from enum import Enum


class Language(Enum):
    KOREAN = "Korean"
    ENGLISH = "English"


class Response(Enum):
    AGAIN = "Again"
    EASY = "Easy"
    GOOD = "Good"
    HARD = "Hard"


class Status(Enum):
    KNOWN = "Known"
    LEARNING = "Learning"
    NEW = "New"
    RELEARNING = "Relearning"
    REVIEW = "Review"
    SUSPENDED = "Suspended"


class POS(Enum):
    VERB = "Verb"
    NOUN = "Noun"
    ADVERB = "Adverb"
    ADJECTIVE = "Adjective"


class MeaningFrequency(Enum):
    COMMON = "Common"
    RARE = "Rare"


class MeaningLabel(Enum):
    ARCHAIC = "Archaic"
    TECHNICAL = "Technical"
