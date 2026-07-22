from enum import Enum

class Language(Enum):
    KOREAN = "Korean"
    ENGLISH = "English"


class Response(Enum):
    KNOWN = "Known"
    EASY = "Easy"
    GOOD = "Good"
    HARD = "Hard"


class Status(Enum):
    KNOWN = "Known"
    LEARNING = "Learning"
    NEW = "New"
    SUSPENDED = "Suspended"


class POS(Enum):
    VERB = "Verb"
    NOUN = "Noun"
    ADVERB = "Adverb"
    ADJECTIVE = "Adjective"
