"""
engine.py — The heart of GhostTyper.
Handles all keystroke simulation logic: timing, typos, fatigue, bursts.
"""

import bisect
import random
import re
import time

from pynput.keyboard import Controller, Key

from core.richtext import FMT_KEYS, parse_rich_text

NEIGHBORS = {
    'a': 'qwsz', 'b': 'vghn', 'c': 'xdfv', 'd': 'ersfxc', 'e': 'wsdr',
    'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yujnbg', 'i': 'ujko', 'j': 'uikmnh',
    'k': 'ijlm', 'l': 'okp', 'm': 'njk', 'n': 'bhjm', 'o': 'iklp',
    'p': 'ol', 'q': 'wa', 'r': 'edft', 's': 'wedxza', 't': 'rfgy',
    'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu', 'z': 'asx'
}

FAST_WORDS = {
    'the', 'and', 'is', 'in', 'it', 'of', 'to', 'a', 'an', 'was',
    'for', 'on', 'are', 'as', 'at', 'be', 'by', 'or', 'but', 'not',
    'this', 'with', 'from', 'that', 'we', 'he', 'she', 'they', 'you', 'i'
}

TRANSPOSITIONS = {
    'the': ['teh', 'hte'],
    'and': ['adn', 'nad'],
    'for': ['fro'],
    'you': ['yuo'],
    'with': ['wiht', 'wtih'],
    'that': ['taht'],
    'have': ['ahve', 'hvae'],
    'from': ['form', 'fomr'],
}


def snap_to_word_start(text: str, index: int) -> int:
    """Snaps a resume index back to the start of the word it lands inside.

    A soft-stop mid-word would otherwise resume mid-word; retyping the whole
    word is cleaner. Indexes on whitespace, at word starts, or at the ends
    are returned untouched.
    """
    index = max(0, min(index, len(text)))
    if 0 < index < len(text) and not text[index - 1].isspace() and not text[index].isspace():
        while index > 0 and not text[index - 1].isspace():
            index -= 1
    return index


def count_words(text: str) -> int:
    """Number of whitespace-separated tokens (the 'word 42/300' total)."""
    return len(re.findall(r'\S+', text))


class TypingEngine:
    def __init__(self, profile: dict, stop_flag: list, emit_hook=None):
        self.profile = profile
        self.stop_flag = stop_flag
        self.emit_hook = emit_hook  # called before each OWN keypress (interference guard)
        self.keyboard = Controller()
        self.chars_typed = 0
        self.fatigue_factor = 1.0
        self.in_burst = False
        self.burst_remaining = 0
        # Resume tracking — index into the *full* text of chars fully completed.
        self.current_index = 0
        self.total = 0
        # Word tracking — spans of non-whitespace for the "word 42/300" view.
        self.word_index = 0
        self.word_total = 0
        self._word_ends: list = []

    def get_progress(self) -> tuple:
        """Returns (current_index, total) for Resume UI."""
        return (self.current_index, self.total)

    def get_word_progress(self) -> tuple:
        """Returns (words_completed, word_total)."""
        return (self.word_index, self.word_total)

    def _sync_word_index(self) -> None:
        self.word_index = bisect.bisect_right(self._word_ends, self.current_index)

    def get_remaining_text(self, text: str) -> str:
        """Text not yet typed (for preview / copy-remaining)."""
        return text[self.current_index:]

    def progress_string(self) -> str:
        return f"{self.current_index}/{self.total} chars"

    def type_text(self, text: str, progress_callback=None, start_index: int = 0) -> bool:
        total = len(text)
        self.total = total
        self._word_ends = [m.end() for m in re.finditer(r'\S+', text)]
        self.word_total = len(self._word_ends)
        # Clamp resume point, snap mid-word stops to the word start, and
        # preserve the fatigue curve across resumes.
        i = snap_to_word_start(text, max(0, min(start_index, total))) if start_index > 0 else 0
        self.current_index = i
        self.chars_typed = i
        self._sync_word_index()
        self._update_fatigue(force=True)
        while i < len(text):
            if self.stop_flag[0]:
                self.current_index = i
                return False

            char = text[i]
            word = self._get_word_at(text, i)

            # NOTE: corrections below are atomic — no stop-check inside
            # _type_with_correction / _type_transposition, so Esc never
            # leaves a half-corrected word on screen.
            if word and word.lower() in TRANSPOSITIONS and self._should_transpose():
                self._type_transposition(word, random.choice(TRANSPOSITIONS[word.lower()]))
                i += len(word)
                self.chars_typed += len(word)
            else:
                self._type_char(char, word)
                i += 1
                self.chars_typed += 1

            self.current_index = i
            self._sync_word_index()
            self._update_fatigue()

            if progress_callback:
                progress_callback(min(i, total), total)

        self.current_index = total
        self._sync_word_index()
        return True

    def _mark(self, key_id: str | None) -> None:
        """Tells the interference guard (via emit_hook) that the next heard
        press is ours. Tolerates legacy zero-arg hooks."""
        if self.emit_hook is None:
            return
        try:
            self.emit_hook(key_id)
        except TypeError:
            try:
                self.emit_hook()
            except Exception:
                pass
        except Exception:
            pass

    def _tap(self, key, key_id: str) -> None:
        """Marked press+release of a special key (backspace, enter)."""
        self._mark(key_id)
        self.keyboard.press(key)
        self.keyboard.release(key)

    def _tap_ctrl(self, letter: str) -> None:
        """Marked Ctrl+letter (bold/italic/underline toggles)."""
        self._mark(letter)
        with self.keyboard.pressed(Key.ctrl):
            self.keyboard.press(letter)
            self.keyboard.release(letter)

    def _apply_heading(self, level: int) -> None:
        """Marked Ctrl+Alt+1/2/3 (works in Word and Google Docs)."""
        num = str(level)
        self._mark(num)
        with self.keyboard.pressed(Key.ctrl, Key.alt):
            self.keyboard.press(num)
            self.keyboard.release(num)

    def _reset_style(self, app: str) -> None:
        """Back to Normal: Word Ctrl+Shift+N, Docs Ctrl+Alt+0."""
        if app == 'docs':
            self._mark('0')
            with self.keyboard.pressed(Key.ctrl, Key.alt):
                self.keyboard.press('0')
                self.keyboard.release('0')
        else:
            self._mark('n')
            with self.keyboard.pressed(Key.ctrl, Key.shift):
                self.keyboard.press('n')
                self.keyboard.release('n')

    def type_rich(self, markup: str, app: str = 'word',
                  progress_callback=None, start_index: int = 0) -> bool:
        """Types markup with real formatting (see core.richtext for syntax).

        Progress (current_index/total, words) is tracked in PLAIN characters
        (markup stripped), so callers should session-track the plain text
        while passing the markup here for typing.
        """
        tokens = parse_rich_text(markup)
        plain = ''.join(t[1] for t in tokens if t[0] == 'text')
        total = len(plain)
        self.total = total
        self._word_ends = [m.end() for m in re.finditer(r'\S+', plain)]
        self.word_total = len(self._word_ends)
        target = snap_to_word_start(plain, max(0, min(start_index, total))) if start_index > 0 else 0

        # Pre-pass: collect fmt/heading state skipped over so a resume
        # re-asserts the style instead of typing styled text plain.
        pending: dict = {}
        pending_heading = None
        pending_list = None
        pos = 0
        rest: list = []
        for tok in tokens:
            if tok[0] == 'text':
                s = tok[1]
                if pos + len(s) <= target:
                    pos += len(s)
                    continue
                if pos < target:
                    rest.append(('text', s[target - pos:]))
                    pos = target
                else:
                    rest.append(tok)
            elif tok[0] == 'fmt':
                if pos < target:
                    pending[tok[1]] = tok[2]
                else:
                    rest.append(tok)
            elif tok[0] == 'heading':
                if pos < target:
                    pending_heading = tok[1]
                else:
                    rest.append(tok)
            else:  # list open/close carries no plain chars; track state
                if pos < target:
                    pending_list = tok[1]
                else:
                    rest.append(tok)

        for name, on in pending.items():
            if on:
                self._tap_ctrl(FMT_KEYS[name])
        active = dict(pending)
        if pending_heading:
            self._apply_heading(pending_heading)
        cur_heading = pending_heading
        # A skipped list-open means its marker was already typed earlier;
        # just continue in that list so the close still exits it cleanly.
        cur_list = pending_list

        i = target
        self.current_index = i
        self.chars_typed = i
        self._sync_word_index()
        self._update_fatigue(force=True)

        for tok in rest:
            if self.stop_flag[0]:
                self.current_index = i
                return False
            if tok[0] == 'text':
                for ch in tok[1]:
                    if self.stop_flag[0]:
                        self.current_index = i
                        return False
                    self._type_char(ch, self._get_word_at(plain, i))
                    i += 1
                    self.chars_typed += 1
                    self.current_index = i
                    self._sync_word_index()
                    self._update_fatigue()
                    if progress_callback:
                        progress_callback(min(i, total), total)
            elif tok[0] == 'fmt':
                _, name, on = tok
                if active.get(name, False) != on:
                    self._tap_ctrl(FMT_KEYS[name])
                    active[name] = on
            elif tok[0] == 'heading':
                level = tok[1]
                if cur_heading != level:
                    if level is None:
                        self._reset_style(app)
                    else:
                        self._apply_heading(level)
                    cur_heading = level
            else:  # list open/close — type the marker, let app autocorrect
                kind = tok[1]  # 'ul' | 'ol' | None
                if kind is None:
                    if cur_list is not None:
                        self._tap(Key.enter, 'key:enter')  # exit list mode
                        cur_list = None
                elif cur_list != kind:
                    for mch in ('- ' if kind == 'ul' else '1. '):
                        self._press_char(mch)
                    cur_list = kind

        self.current_index = total
        self._sync_word_index()
        return True

    def _type_char(self, char: str, current_word: str = '') -> None:
        if self._should_make_typo(char):
            self._type_with_correction(char)
        else:
            self._press_char(char)
        delay = self._calculate_delay(char, current_word)
        time.sleep(delay)

    def _type_with_correction(self, char: str) -> None:
        wrong = random.choice(NEIGHBORS[char.lower()])
        if char.isupper():
            wrong = wrong.upper()
        self._press_char(wrong)
        time.sleep(random.uniform(0.08, 0.22))
        self._tap(Key.backspace, 'key:backspace')
        time.sleep(random.uniform(0.12, 0.28))
        self._press_char(char)

    def _type_transposition(self, correct_word: str, typo_word: str) -> None:
        for ch in typo_word:
            self._press_char(ch)
            time.sleep(random.uniform(0.04, 0.10))
        time.sleep(random.uniform(0.15, 0.35))
        for _ in typo_word:
            self._tap(Key.backspace, 'key:backspace')
            time.sleep(random.uniform(0.04, 0.09))
        time.sleep(random.uniform(0.10, 0.20))
        for ch in correct_word:
            self._press_char(ch)
            time.sleep(random.uniform(0.04, 0.10))

    def _press_char(self, char: str) -> None:
        """Low-level key press with safe handling of special characters."""
        # Always skip carriage return (emits nothing — mark nothing)
        if char == '\r':
            return

        # Tab key would move focus / click buttons — convert to spaces
        if char == '\t':
            self._mark(' ')
            self.keyboard.type('    ')  # 4 spaces, safe everywhere
            return

        # Newline handling
        if char == '\n':
            self._mark('key:enter')
            if self.profile.get('chat_mode', False):
                # Shift+Enter = newline without submitting in chat UIs
                # (shift itself is in the interference guard's ignore set)
                with self.keyboard.pressed(Key.shift):
                    self.keyboard.press(Key.enter)
                    self.keyboard.release(Key.enter)
            else:
                # Normal Enter for Word, Notepad, Docs
                self.keyboard.press(Key.enter)
                self.keyboard.release(Key.enter)
            return

        # Everything else — letters, numbers, punctuation, symbols.
        # Astral chars (emoji) are heard by the listener as lone-surrogate
        # halves, so mark the shared id (see controller._key_id).
        lowered = char.lower()
        if len(char) == 1 and ord(char) > 0xFFFF:
            self._mark('surrogate-half')
        else:
            self._mark(lowered)
        self.keyboard.type(char)

    def _calculate_delay(self, char: str, current_word: str = '') -> float:
        p = self.profile
        base = 60.0 / (p['wpm'] * 5)

        # Mechanical typewriter rhythm: steady clack, no bursts.
        if p.get('mechanical', False):
            delay = base * random.uniform(0.9, 1.1)
            if current_word and current_word.lower() in FAST_WORDS:
                delay *= 0.9
            if char in '.!?':
                delay += random.uniform(0.25, 0.5)
            elif char in ',;:':
                delay += random.uniform(0.1, 0.25)
            elif char == ' ':
                delay += random.uniform(0.02, 0.06)
            elif char == '\n':
                # carriage-return clunk
                delay += random.uniform(0.7, 1.1)
            if random.random() < p.get('thinking_chance', 0.004):
                delay += random.uniform(0.8, 2.0)
            delay *= self.fatigue_factor
            return max(delay, 0.02)

        delay = base * random.uniform(0.6, 1.4)

        if self.in_burst:
            delay *= 0.55
            self.burst_remaining -= 1
            if self.burst_remaining <= 0:
                self.in_burst = False
        elif random.random() < p.get('burst_chance', 0.05):
            self.in_burst = True
            self.burst_remaining = random.randint(8, 20)

        if current_word and current_word.lower() in FAST_WORDS:
            delay *= 0.75

        if char in '.!?':
            delay += random.uniform(0.4, 1.2)
        elif char in ',;:':
            delay += random.uniform(0.15, 0.5)
        elif char == ' ':
            delay += random.uniform(0.02, 0.08)
        elif char == '\n':
            delay += random.uniform(0.6, 1.8)

        if random.random() < p.get('thinking_chance', 0.012):
            delay += random.uniform(1.2, 3.5)

        delay *= self.fatigue_factor
        return max(delay, 0.02)

    def _update_fatigue(self, force: bool = False) -> None:
        if not self.profile.get('fatigue_enabled', True):
            return
        if force or self.chars_typed % 100 == 0:
            self.fatigue_factor = min(1.0 + (self.chars_typed / 4000), 1.25)

    def _should_make_typo(self, char: str) -> bool:
        if not self.profile.get('errors_enabled', True):
            return False
        if char.lower() not in NEIGHBORS:
            return False
        return random.random() < self.profile.get('error_rate', 0.04)

    def _should_transpose(self) -> bool:
        if not self.profile.get('errors_enabled', True):
            return False
        return random.random() < self.profile.get('transposition_rate', 0.008)

    def _get_word_at(self, text: str, index: int) -> str:
        if not text[index].isalpha():
            return ''
        end = index
        while end < len(text) and text[end].isalpha():
            end += 1
        return text[index:end]