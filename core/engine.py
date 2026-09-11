"""
engine.py — The heart of GhostTyper.
Handles all keystroke simulation logic: timing, typos, fatigue, bursts.
"""

import random
import time

from pynput.keyboard import Controller, Key

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

    def get_progress(self) -> tuple:
        """Returns (current_index, total) for Resume UI."""
        return (self.current_index, self.total)

    def get_remaining_text(self, text: str) -> str:
        """Text not yet typed (for preview / copy-remaining)."""
        return text[self.current_index:]

    def progress_string(self) -> str:
        return f"{self.current_index}/{self.total} chars"

    def type_text(self, text: str, progress_callback=None, start_index: int = 0) -> bool:
        total = len(text)
        self.total = total
        # Clamp resume point; preserve fatigue curve across resumes.
        i = max(0, min(start_index, total))
        self.current_index = i
        self.chars_typed = i
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
            self._update_fatigue()

            if progress_callback:
                progress_callback(min(i, total), total)

        self.current_index = total
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
        self.keyboard.press(Key.backspace)
        self.keyboard.release(Key.backspace)
        time.sleep(random.uniform(0.12, 0.28))
        self._press_char(char)

    def _type_transposition(self, correct_word: str, typo_word: str) -> None:
        for ch in typo_word:
            self._press_char(ch)
            time.sleep(random.uniform(0.04, 0.10))
        time.sleep(random.uniform(0.15, 0.35))
        for _ in typo_word:
            self.keyboard.press(Key.backspace)
            self.keyboard.release(Key.backspace)
            time.sleep(random.uniform(0.04, 0.09))
        time.sleep(random.uniform(0.10, 0.20))
        for ch in correct_word:
            self._press_char(ch)
            time.sleep(random.uniform(0.04, 0.10))

    def _press_char(self, char: str) -> None:
        """Low-level key press with safe handling of special characters."""
        if self.emit_hook is not None:
            try:
                self.emit_hook()
            except Exception:
                pass

        # Always skip carriage return
        if char == '\r':
            return

        # Tab key would move focus / click buttons — convert to spaces
        if char == '\t':
            self.keyboard.type('    ')  # 4 spaces, safe everywhere
            return

        # Newline handling
        if char == '\n':
            if self.profile.get('chat_mode', False):
                # Shift+Enter = newline without submitting in chat UIs
                with self.keyboard.pressed(Key.shift):
                    self.keyboard.press(Key.enter)
                    self.keyboard.release(Key.enter)
            else:
                # Normal Enter for Word, Notepad, Docs
                self.keyboard.press(Key.enter)
                self.keyboard.release(Key.enter)
            return

        # Everything else — letters, numbers, punctuation, symbols
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