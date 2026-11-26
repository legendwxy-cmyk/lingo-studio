from __future__ import annotations

import html
import re
import warnings
from typing import Any

import eng_to_ipa as ipa_lib

warnings.filterwarnings("ignore", category=SyntaxWarning, module="eng_to_ipa")

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "while", "where",
    "who", "whom", "whose", "which", "what", "that", "this", "these", "those",
    "i", "me", "my", "mine", "myself", "you", "your", "yours", "yourself",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall", "should",
    "can", "could", "may", "might", "must",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "into", "onto",
    "over", "under", "up", "down", "out", "off", "as", "than", "so", "not", "no", "nor",
    "very", "too", "also", "just", "only", "more", "most", "much", "many", "some", "any",
    "all", "both", "each", "every", "other", "another", "such", "here", "there", "now",
    "well", "like", "even", "still", "back", "one", "two", "three", "first", "second",
    "don't", "doesn't", "didn't", "won't", "wouldn't", "can't", "couldn't", "isn't",
    "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't", "it's", "that's",
    "i'm", "you're", "we're", "they're", "he's", "she's", "i've", "we've", "you've",
    "let's", "there's", "what's", "who's", "really", "actually", "basically", "thing",
    "things", "get", "got", "go", "going", "went", "gone", "make", "made", "take", "took",
    "say", "said", "see", "saw", "know", "knew", "think", "thought", "come", "came",
    "want", "use", "used", "using", "way", "time", "day", "year", "people", "man", "woman",
}

IRREGULAR_LEMMAS: dict[str, str] = {
    "woke": "wake", "woken": "wake", "flew": "fly", "flown": "fly",
    "began": "begin", "begun": "begin", "broke": "break", "broken": "break",
    "built": "build", "caught": "catch", "chose": "choose", "chosen": "choose",
    "dealt": "deal", "drew": "draw", "drawn": "draw", "drove": "drive", "driven": "drive",
    "fell": "fall", "fallen": "fall", "felt": "feel", "found": "find",
    "forgot": "forget", "forgotten": "forget", "grew": "grow", "grown": "grow",
    "heard": "hear", "held": "hold", "kept": "keep", "led": "lead", "left": "leave",
    "lost": "lose", "meant": "mean", "met": "meet", "paid": "pay", "ran": "run",
    "rose": "rise", "risen": "rise", "sent": "send", "set": "set", "shook": "shake",
    "shown": "show", "showed": "show", "sat": "sit", "slept": "sleep", "spoke": "speak",
    "spoken": "speak", "spent": "spend", "stood": "stand", "stuck": "stick",
    "taught": "teach", "told": "tell", "understood": "understand", "won": "win",
    "wrote": "write", "written": "write", "brought": "bring", "bought": "buy",
    "children": "child", "men": "man", "women": "woman", "feet": "foot", "teeth": "tooth",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "habits": "habit", "studies": "study", "stories": "story", "memories": "memory",
    "strategies": "strategy", "abilities": "ability", "activities": "activity",
}

# Built-in curated academic & spoken English-Chinese lexicon (phrases + words)
CURATED_LEXICON: dict[str, dict[str, Any]] = {
    # --- Phrasal verbs & multi-word expressions ---
    "break down": {
        "headword": "break down",
        "category": "短语动词",
        "patterns": [r"\b(?:break|breaks|breaking|broke|broken)\s+down\b"],
        "exam_tags": ["四级", "雅思", "口语"],
        "ipa_us": "/breɪk daʊn/",
        "ipa_uk": "/breɪk daʊn/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to divide something complex into smaller, easier parts in order to understand or handle it",
                "definition_target": "拆解；将复杂内容分解为更小的部分",
                "usage_pattern": "break down + noun / break + noun + down",
                "examples": [
                    {
                        "example_source": "Break down a dense lecture into ten-second clips so every phrase sinks in.",
                        "example_target": "把晦涩的讲座拆解成十秒片段，让每个表达都能真正吸收。",
                    }
                ],
            }
        ],
    },
    "sink in": {
        "headword": "sink in",
        "category": "短语动词",
        "patterns": [r"\b(?:sink|sinks|sinking|sank|sunk)\s+in\b"],
        "exam_tags": ["六级", "雅思", "口语"],
        "ipa_us": "/sɪŋk ɪn/",
        "ipa_uk": "/sɪŋk ɪn/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to become fully understood, absorbed, or realized gradually",
                "definition_target": "（知识、事实等）逐渐被理解、消化吸收",
                "usage_pattern": "let something sink in",
                "examples": [
                    {
                        "example_source": "Pause for two seconds after each sentence to let the rhythm sink in.",
                        "example_target": "每句之后停顿两秒，让语流节奏慢慢沉淀吸收。",
                    }
                ],
            }
        ],
    },
    "focus on": {
        "headword": "focus on",
        "category": "短语动词",
        "patterns": [r"\b(?:focus|focuses|focused|focusing)\s+on\b"],
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/ˈfoʊkəs ɑːn/",
        "ipa_uk": "/ˈfəʊkəs ɒn/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to direct your attention or effort toward a specific subject or goal",
                "definition_target": "专注于；把注意力集中在",
                "usage_pattern": "focus on + noun / doing",
                "examples": [
                    {
                        "example_source": "Focus on one short scene rather than skimming an entire movie.",
                        "example_target": "专注于一个短片段，而不是走马观花地刷完一整部电影。",
                    }
                ],
            }
        ],
    },
    "pick up": {
        "headword": "pick up",
        "category": "短语动词",
        "patterns": [r"\b(?:pick|picks|picked|picking)\s+up\b"],
        "exam_tags": ["四级", "口语", "雅思"],
        "ipa_us": "/pɪk ʌp/",
        "ipa_uk": "/pɪk ʌp/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to learn a skill, language, or habit naturally through exposure and practice",
                "definition_target": "（在语境中自然地）学会、习得；捕捉到（细节/语音）",
                "usage_pattern": "pick up + language/expression/accent",
                "examples": [
                    {
                        "example_source": "You quickly pick up natural phrasing when you shadow native speakers daily.",
                        "example_target": "每天坚持影子跟读母语者，你很快就能自然习得地道表达。",
                    }
                ],
            }
        ],
    },
    "figure out": {
        "headword": "figure out",
        "category": "短语动词",
        "patterns": [r"\b(?:figure|figures|figured|figuring)\s+out\b"],
        "exam_tags": ["四级", "口语", "托福"],
        "ipa_us": "/ˈfɪɡjər aʊt/",
        "ipa_uk": "/ˈfɪɡər aʊt/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to understand or solve something through careful thought or listening",
                "definition_target": "弄明白；想出；听懂并理清",
                "usage_pattern": "figure out + wh-clause / noun",
                "examples": [
                    {
                        "example_source": "Replay the clip until you figure out where the speaker links the consonants.",
                        "example_target": "反复重播这个片段，直到你听清说话者在哪里发生了辅音连读。",
                    }
                ],
            }
        ],
    },
    "pay attention to": {
        "headword": "pay attention to",
        "category": "搭配",
        "patterns": [r"\b(?:pay|pays|paid|paying)\s+(?:close\s+)?attention\s+to\b"],
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/peɪ əˈtɛnʃən tuː/",
        "ipa_uk": "/peɪ əˈtɛnʃən tuː/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to listen to, watch, or consider someone or something carefully",
                "definition_target": "留意；密切关注",
                "usage_pattern": "pay (close) attention to + noun",
                "examples": [
                    {
                        "example_source": "Pay close attention to stressed syllables and rising intonation.",
                        "example_target": "请特别留意重读音节以及上扬的语调变化。",
                    }
                ],
            }
        ],
    },
    "in the long run": {
        "headword": "in the long run",
        "category": "惯用表达",
        "patterns": [r"\bin\s+the\s+long\s+run\b"],
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/ɪn ðə lɔːŋ rʌn/",
        "ipa_uk": "/ɪn ðə lɒŋ rʌn/",
        "definitions": [
            {
                "pos": "idiom",
                "definition_source": "over a long period of time; eventually, looking beyond immediate results",
                "definition_target": "从长远来看；最终",
                "usage_pattern": "sentence adverbial",
                "examples": [
                    {
                        "example_source": "Fifteen minutes of deliberate listening pays off dramatically in the long run.",
                        "example_target": "每天十五分钟的刻意精听，从长远来看会带来惊人的回报。",
                    }
                ],
            }
        ],
    },
    "pay off": {
        "headword": "pay off",
        "category": "短语动词",
        "patterns": [r"\b(?:pay|pays|paid|paying)\s+off\b"],
        "exam_tags": ["六级", "雅思", "口语"],
        "ipa_us": "/peɪ ɔːf/",
        "ipa_uk": "/peɪ ɒf/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to produce good results or bring a worthwhile reward after sustained effort",
                "definition_target": "取得回报；见效；没有白费",
                "usage_pattern": "effort / practice pays off",
                "examples": [
                    {
                        "example_source": "Consistent shadowing always pays off when you step into a real conversation.",
                        "example_target": "当你走进真实对话时，持续的影子跟读一定会见效。",
                    }
                ],
            }
        ],
    },
    "step by step": {
        "headword": "step by step",
        "category": "搭配",
        "patterns": [r"\bstep\s+by\s+step\b"],
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/stɛp baɪ stɛp/",
        "ipa_uk": "/stɛp baɪ stɛp/",
        "definitions": [
            {
                "pos": "adverbial phrase",
                "definition_source": "gradually, moving carefully from one stage to the next in sequence",
                "definition_target": "循序渐进地；一步一步地",
                "usage_pattern": "verb + step by step",
                "examples": [
                    {
                        "example_source": "Build fluency step by step: blind listening first, then dictation and shadowing.",
                        "example_target": "循序渐进地建立流利度：先盲听，再听写与跟读。",
                    }
                ],
            }
        ],
    },
    "out loud": {
        "headword": "out loud",
        "category": "搭配",
        "patterns": [r"\bout\s+loud\b"],
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/aʊt laʊd/",
        "ipa_uk": "/aʊt laʊd/",
        "definitions": [
            {
                "pos": "adverbial phrase",
                "definition_source": "audibly, with your speaking voice rather than silently in your head",
                "definition_target": "大声地；出声地",
                "usage_pattern": "read / speak / repeat out loud",
                "examples": [
                    {
                        "example_source": "Always repeat the line out loud so your mouth builds muscle memory.",
                        "example_target": "务必大声复述句子，让口腔建立肌肉记忆。",
                    }
                ],
            }
        ],
    },
    "wake up": {
        "headword": "wake up",
        "category": "短语动词",
        "patterns": [r"\b(?:wake|wakes|woke|woken|waking)\s+up\b"],
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/weɪk ʌp/",
        "ipa_uk": "/weɪk ʌp/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to stop sleeping and become conscious",
                "definition_target": "醒来；唤醒",
                "usage_pattern": "wake up (early / at + time)",
                "examples": [
                    {
                        "example_source": "He woke up before dawn and listened to a five-minute podcast.",
                        "example_target": "他黎明前醒来，听了一段五分钟的播客。",
                    }
                ],
            }
        ],
    },
    "turn into": {
        "headword": "turn into",
        "category": "短语动词",
        "patterns": [r"\b(?:turn|turns|turned|turning)\s+(?:\w+\s+)?into\b"],
        "exam_tags": ["四级", "六级"],
        "ipa_us": "/tɜːrn ˈɪntuː/",
        "ipa_uk": "/tɜːn ˈɪntuː/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to transform or convert something into a different form or state",
                "definition_target": "把……转化为；变成",
                "usage_pattern": "turn A into B",
                "examples": [
                    {
                        "example_source": "Turn passive watching into active speaking practice.",
                        "example_target": "把被动的看视频转化为主动的口语训练。",
                    }
                ],
            }
        ],
    },
    "rely on": {
        "headword": "rely on",
        "category": "短语动词",
        "patterns": [r"\b(?:rely|relies|relied|relying)\s+on\b"],
        "exam_tags": ["四级", "雅思", "托福"],
        "ipa_us": "/rɪˈlaɪ ɑːn/",
        "ipa_uk": "/rɪˈlaɪ ɒn/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to depend on someone or something with trust or necessity",
                "definition_target": "依赖；依靠",
                "usage_pattern": "rely on + noun / doing",
                "examples": [
                    {
                        "example_source": "Try not to rely on Chinese subtitles on your second pass.",
                        "example_target": "第二遍听的时候，尽量不要依赖中文字幕。",
                    }
                ],
            }
        ],
    },
    "keep track of": {
        "headword": "keep track of",
        "category": "惯用表达",
        "patterns": [r"\b(?:keep|keeps|kept|keeping)\s+track\s+of\b"],
        "exam_tags": ["六级", "雅思", "口语"],
        "ipa_us": "/kiːp træk ʌv/",
        "ipa_uk": "/kiːp træk əv/",
        "definitions": [
            {
                "pos": "idiom",
                "definition_source": "to continue to record or stay aware of the progress or status of something",
                "definition_target": "记录；持续追踪……的进展",
                "usage_pattern": "keep track of + noun",
                "examples": [
                    {
                        "example_source": "Use a personal lexicon to keep track of every tricky collocation.",
                        "example_target": "用个人生词索引来记录每一个棘手的固定搭配。",
                    }
                ],
            }
        ],
    },
    "muscle memory": {
        "headword": "muscle memory",
        "category": "搭配",
        "patterns": [r"\bmuscle\s+memory\b"],
        "exam_tags": ["雅思", "口语"],
        "ipa_us": "/ˈmʌsəl ˈmɛməri/",
        "ipa_uk": "/ˈmʌsəl ˈmɛməri/",
        "definitions": [
            {
                "pos": "noun phrase",
                "definition_source": "the ability to reproduce a physical movement or pronunciation pattern automatically through repetition",
                "definition_target": "肌肉记忆（口语中指反复跟读形成的条件反射发音能力）",
                "usage_pattern": "build / develop muscle memory",
                "examples": [
                    {
                        "example_source": "Shadowing builds vocal muscle memory faster than silent reading.",
                        "example_target": "影子跟读比默读能更快建立口腔肌肉记忆。",
                    }
                ],
            }
        ],
    },
    "stand out": {
        "headword": "stand out",
        "category": "短语动词",
        "patterns": [r"\b(?:stand|stands|stood|standing)\s+out\b"],
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/stænd aʊt/",
        "ipa_uk": "/stænd aʊt/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to be immediately noticeable or clearly superior compared to surroundings",
                "definition_target": "脱颖而出；格外显眼；突出",
                "usage_pattern": "stand out from / in",
                "examples": [
                    {
                        "example_source": "Key idioms stand out clearly when underlined in context.",
                        "example_target": "重点习语在语境中加上下划线后会格外清晰突出。",
                    }
                ],
            }
        ],
    },
    "cut down": {
        "headword": "cut down",
        "category": "短语动词",
        "patterns": [r"\b(?:cut|cuts|cutting)\s+down(?:\s+on)?\b"],
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/kʌt daʊn/",
        "ipa_uk": "/kʌt daʊn/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to reduce the amount, size, or frequency of something",
                "definition_target": "削减；减少",
                "usage_pattern": "cut down (on) + noun",
                "examples": [
                    {
                        "example_source": "Cut down on multitasking when practicing intensive listening.",
                        "example_target": "进行精听训练时要减少多线程分心。",
                    }
                ],
            }
        ],
    },
    "make sense": {
        "headword": "make sense",
        "category": "搭配",
        "patterns": [r"\b(?:make|makes|made|making)\s+sense\b"],
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/meɪk sɛns/",
        "ipa_uk": "/meɪk sɛns/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to be intelligible, logical, or reasonable",
                "definition_target": "讲得通；有道理；容易理解",
                "usage_pattern": "make sense (to someone)",
                "examples": [
                    {
                        "example_source": "Once you hear the stress pattern, the whole sentence makes sense.",
                        "example_target": "一旦听清重音规律，整句话立刻就通顺了。",
                    }
                ],
            }
        ],
    },
    "end up": {
        "headword": "end up",
        "category": "短语动词",
        "patterns": [r"\b(?:end|ends|ended|ending)\s+up\b"],
        "exam_tags": ["四级", "口语", "雅思"],
        "ipa_us": "/ɛnd ʌp/",
        "ipa_uk": "/ɛnd ʌp/",
        "definitions": [
            {
                "pos": "verb phrase",
                "definition_source": "to eventually reach a particular state, place, or outcome",
                "definition_target": "最终落得；结果成为",
                "usage_pattern": "end up + doing / adj / prep",
                "examples": [
                    {
                        "example_source": "Learners who skip review often end up forgetting half the phrases.",
                        "example_target": "跳过复习的学习者最终往往会忘掉一半短语。",
                    }
                ],
            }
        ],
    },
    # --- High-value single words ---
    "deliberate": {
        "headword": "deliberate",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/dɪˈlɪbərət/",
        "ipa_uk": "/dɪˈlɪbərət/",
        "definitions": [
            {
                "pos": "adjective",
                "definition_source": "done consciously, intentionally, and with careful focus on improvement",
                "definition_target": "刻意的；深思熟虑的；有意识的",
                "usage_pattern": "deliberate practice / deliberate effort",
                "examples": [
                    {
                        "example_source": "Deliberate practice targets the exact syllables you struggle to hear.",
                        "example_target": "刻意练习会精准瞄准那些你最难听清的音节。",
                    }
                ],
            }
        ],
    },
    "fluency": {
        "headword": "fluency",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "口语"],
        "ipa_us": "/ˈfluːənsi/",
        "ipa_uk": "/ˈfluːənsi/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the ability to speak or write a language easily, smoothly, and accurately",
                "definition_target": "流利度；流畅自如的表达能力",
                "usage_pattern": "build / achieve fluency in",
                "examples": [
                    {
                        "example_source": "True fluency grows from absorbing natural rhythm, not memorizing isolated lists.",
                        "example_target": "真正的流利源于吸收自然语流，而非死记孤立词表。",
                    }
                ],
            }
        ],
    },
    "rhythm": {
        "headword": "rhythm",
        "category": "单词",
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/ˈrɪðəm/",
        "ipa_uk": "/ˈrɪðəm/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a strong, regular repeated pattern of sound, stress, and timing in speech",
                "definition_target": "节奏；韵律；语流律动",
                "usage_pattern": "natural rhythm of English",
                "examples": [
                    {
                        "example_source": "Imitating the speaker's rhythm makes your accent sound far more natural.",
                        "example_target": "模仿说话者的语流节奏会让你的发音自然得多。",
                    }
                ],
            }
        ],
    },
    "intonation": {
        "headword": "intonation",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "口语"],
        "ipa_us": "/ˌɪntəˈneɪʃən/",
        "ipa_uk": "/ˌɪntəˈneɪʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the rise and fall of the voice pitch in speaking, conveying attitude and meaning",
                "definition_target": "语调；声调起伏",
                "usage_pattern": "rising / falling intonation",
                "examples": [
                    {
                        "example_source": "Notice how rising intonation turns a plain statement into a polite question.",
                        "example_target": "注意上扬语调如何把一句平铺直叙的陈述变成礼貌的提问。",
                    }
                ],
            }
        ],
    },
    "authentic": {
        "headword": "authentic",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/ɔːˈθɛntɪk/",
        "ipa_uk": "/ɔːˈθɛntɪk/",
        "definitions": [
            {
                "pos": "adjective",
                "definition_source": "genuine, real, and drawn directly from natural everyday usage rather than textbook scripts",
                "definition_target": "地道的；真实的；原汁原味的",
                "usage_pattern": "authentic material / authentic dialogue",
                "examples": [
                    {
                        "example_source": "Studying authentic interviews trains your ear for real-world speed.",
                        "example_target": "精听原汁原味的访谈素材能训练耳朵适应真实语速。",
                    }
                ],
            }
        ],
    },
    "context": {
        "headword": "context",
        "category": "单词",
        "exam_tags": ["四级", "雅思", "托福"],
        "ipa_us": "/ˈkɑːntɛkst/",
        "ipa_uk": "/ˈkɒntɛkst/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the surrounding words, situation, or scene that clarify the exact meaning of an expression",
                "definition_target": "语境；上下文；背景情境",
                "usage_pattern": "in context / out of context",
                "examples": [
                    {
                        "example_source": "Vocabulary sticks three times longer when learned in vivid video context.",
                        "example_target": "在生动的视频语境中学习词汇，记忆留存时间会延长三倍。",
                    }
                ],
            }
        ],
    },
    "consistent": {
        "headword": "consistent",
        "category": "单词",
        "exam_tags": ["四级", "六级", "雅思"],
        "ipa_us": "/kənˈsɪstənt/",
        "ipa_uk": "/kənˈsɪstənt/",
        "definitions": [
            {
                "pos": "adjective",
                "definition_source": "acting or done in the same steady, reliable way over time",
                "definition_target": "持续稳定的；一以贯之的",
                "usage_pattern": "stay consistent / consistent habit",
                "examples": [
                    {
                        "example_source": "A consistent ten-minute daily ritual beats an exhausting weekend marathon.",
                        "example_target": "每天稳定坚持十分钟，胜过周末精疲力竭的突击恶补。",
                    }
                ],
            }
        ],
    },
    "attention": {
        "headword": "attention",
        "category": "单词",
        "exam_tags": ["四级"],
        "ipa_us": "/əˈtɛnʃən/",
        "ipa_uk": "/əˈtɛnʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "focused mental notice or concentration directed at something",
                "definition_target": "注意力；专注；关注",
                "usage_pattern": "hold / capture / direct attention",
                "examples": [
                    {
                        "example_source": "Protect your morning attention before opening any message feed.",
                        "example_target": "在打开任何消息流之前，先守住你清晨的专注力。",
                    }
                ],
            }
        ],
    },
    "distraction": {
        "headword": "distraction",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/dɪˈstrækʃən/",
        "ipa_uk": "/dɪˈstrækʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "something that diverts your focus and prevents you from concentrating fully",
                "definition_target": "干扰；分心之物；注意力分散",
                "usage_pattern": "remove / minimize distractions",
                "examples": [
                    {
                        "example_source": "Removing visual distractions helps your ears lock onto subtle vowels.",
                        "example_target": "排除视觉干扰能让耳朵牢牢锁定细微的元音变化。",
                    }
                ],
            }
        ],
    },
    "passive": {
        "headword": "passive",
        "category": "单词",
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/ˈpæsɪv/",
        "ipa_uk": "/ˈpæsɪv/",
        "definitions": [
            {
                "pos": "adjective",
                "definition_source": "receiving input without actively responding, recalling, or producing output",
                "definition_target": "被动的；消极接收的",
                "usage_pattern": "passive listening / passive vocabulary",
                "examples": [
                    {
                        "example_source": "Passive background audio rarely improves speaking precision by itself.",
                        "example_target": "单靠被动的背景磨耳朵很难真正提升口语精准度。",
                    }
                ],
            }
        ],
    },
    "active": {
        "headword": "active",
        "category": "单词",
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/ˈæktɪv/",
        "ipa_uk": "/ˈæktɪv/",
        "definitions": [
            {
                "pos": "adjective",
                "definition_source": "engaged in intentional recall, output, and deliberate effort",
                "definition_target": "主动的；积极运用的",
                "usage_pattern": "active recall / active vocabulary",
                "examples": [
                    {
                        "example_source": "Cloze drills convert passive recognition into active recall.",
                        "example_target": "挖空训练能把被动认词转化为主动回忆。",
                    }
                ],
            }
        ],
    },
    "dictation": {
        "headword": "dictation",
        "category": "单词",
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/dɪkˈteɪʃən/",
        "ipa_uk": "/dɪkˈteɪʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the exercise of writing down spoken language word for word to reveal listening blind spots",
                "definition_target": "听写；精听听写训练",
                "usage_pattern": "practice dictation / dictation drill",
                "examples": [
                    {
                        "example_source": "Short dictation exercises instantly expose the weak syllables you missed.",
                        "example_target": "短句听写训练能立刻暴露你漏听的弱读音节。",
                    }
                ],
            }
        ],
    },
    "shadowing": {
        "headword": "shadowing",
        "category": "单词",
        "exam_tags": ["口语", "雅思"],
        "ipa_us": "/ˈʃædoʊɪŋ/",
        "ipa_uk": "/ˈʃædəʊɪŋ/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a language learning technique where you repeat speech aloud right behind a speaker",
                "definition_target": "影子跟读法；同步模仿跟读",
                "usage_pattern": "practice shadowing / shadowing session",
                "examples": [
                    {
                        "example_source": "Record your shadowing attempt and compare it directly against the original voice.",
                        "example_target": "录下你的影子跟读，并与原声直接对照检查差距。",
                    }
                ],
            }
        ],
    },
    "syllable": {
        "headword": "syllable",
        "category": "单词",
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/ˈsɪləbəl/",
        "ipa_uk": "/ˈsɪləbəl/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a single unit of pronunciation containing a vowel sound, with or without surrounding consonants",
                "definition_target": "音节",
                "usage_pattern": "stressed / unstressed syllable",
                "examples": [
                    {
                        "example_source": "English speakers compress unstressed syllables much faster than beginners expect.",
                        "example_target": "英语母语者压缩非重读音节的速度远超初学者预期。",
                    }
                ],
            }
        ],
    },
    "pronunciation": {
        "headword": "pronunciation",
        "category": "单词",
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/prəˌnʌnsiˈeɪʃən/",
        "ipa_uk": "/prəˌnʌnsiˈeɪʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the way in which a word or sentence is spoken aloud",
                "definition_target": "发音；读音",
                "usage_pattern": "clear / accurate pronunciation",
                "examples": [
                    {
                        "example_source": "Checking phonetic symbols clarifies tricky pronunciation differences.",
                        "example_target": "对照国际音标能理清容易混淆的发音细节。",
                    }
                ],
            }
        ],
    },
    "retention": {
        "headword": "retention",
        "category": "单词",
        "exam_tags": ["六级", "托福", "雅思"],
        "ipa_us": "/rɪˈtɛnʃən/",
        "ipa_uk": "/rɪˈtɛnʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the continued possession or memory of facts, vocabulary, and skills over time",
                "definition_target": "记忆留存；保持率",
                "usage_pattern": "memory / vocabulary retention",
                "examples": [
                    {
                        "example_source": "Replaying a word across multiple scenes dramatically boosts retention.",
                        "example_target": "在多个不同场景中重温同一个词会极大提升记忆留存率。",
                    }
                ],
            }
        ],
    },
    "clarity": {
        "headword": "clarity",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/ˈklærəti/",
        "ipa_uk": "/ˈklærəti/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the quality of being clear, coherent, and immediately easy to understand",
                "definition_target": "清晰度；明晰；透彻",
                "usage_pattern": "speak with clarity / mental clarity",
                "examples": [
                    {
                        "example_source": "Slow down to 0.8x speed whenever you need extra clarity on fast phrasing.",
                        "example_target": "遇到语速较快的表达时，切到 0.8 倍速可以获得更高清晰度。",
                    }
                ],
            }
        ],
    },
    "precision": {
        "headword": "precision",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/prɪˈsɪʒən/",
        "ipa_uk": "/prɪˈsɪʒən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the quality of being exact, accurate, and finely detailed",
                "definition_target": "精确度；精准",
                "usage_pattern": "with precision",
                "examples": [
                    {
                        "example_source": "Segment-by-segment looping lets you study dialogue with surgical precision.",
                        "example_target": "逐句循环让你能够以极其精准的方式剖析对话。",
                    }
                ],
            }
        ],
    },
    "subtle": {
        "headword": "subtle",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/ˈsʌtəl/",
        "ipa_uk": "/ˈsʌtəl/",
        "definitions": [
            {
                "pos": "adjective",
                "definition_source": "so delicate or precise as to be difficult to notice without close attention",
                "definition_target": "细微的；微妙的；不易察觉的",
                "usage_pattern": "subtle difference / subtle nuance",
                "examples": [
                    {
                        "example_source": "Listen closely for the subtle pause before the final clause.",
                        "example_target": "仔细听最后一个分句之前那处微妙的停顿。",
                    }
                ],
            }
        ],
    },
    "nuance": {
        "headword": "nuance",
        "category": "单词",
        "exam_tags": ["雅思", "托福", "考研"],
        "ipa_us": "/ˈnuːɑːns/",
        "ipa_uk": "/ˈnjuːɑːns/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a very slight difference in meaning, tone, or expression",
                "definition_target": "细微差别；语感层次",
                "usage_pattern": "capture the nuance of",
                "examples": [
                    {
                        "example_source": "Real clips reveal emotional nuance that plain dictionary lines miss.",
                        "example_target": "真实视频片段能展现出普通词典词条无法传达的情感细微差别。",
                    }
                ],
            }
        ],
    },
    "ritual": {
        "headword": "ritual",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/ˈrɪtʃuəl/",
        "ipa_uk": "/ˈrɪtʃuəl/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a regular, structured series of habits performed consistently in a set order",
                "definition_target": "固定习惯；日常仪式感",
                "usage_pattern": "morning / daily study ritual",
                "examples": [
                    {
                        "example_source": "Turn one short clip into a calm ten-minute morning ritual.",
                        "example_target": "把一个短视频变成每天清晨沉静的十分钟学习习惯。",
                    }
                ],
            }
        ],
    },
    "momentum": {
        "headword": "momentum",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/moʊˈmɛntəm/",
        "ipa_uk": "/məʊˈmɛntəm/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the driving force or speed gained by steady, continuous progress",
                "definition_target": "势头；动力；推进力",
                "usage_pattern": "build / maintain momentum",
                "examples": [
                    {
                        "example_source": "Small daily wins create unstoppable learning momentum.",
                        "example_target": "每天小小的完成感会积蓄出势不可挡的学习势头。",
                    }
                ],
            }
        ],
    },
    "confidence": {
        "headword": "confidence",
        "category": "单词",
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/ˈkɑːnfɪdəns/",
        "ipa_uk": "/ˈkɒnfɪdəns/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a feeling of self-assurance arising from competence and preparation",
                "definition_target": "自信；把握",
                "usage_pattern": "speak with confidence / build confidence",
                "examples": [
                    {
                        "example_source": "Hearing your own clean recording immediately builds speaking confidence.",
                        "example_target": "听到自己清晰流畅的录音会立刻建立开口自信。",
                    }
                ],
            }
        ],
    },
    "routine": {
        "headword": "routine",
        "category": "单词",
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/ruːˈtiːn/",
        "ipa_uk": "/ruːˈtiːn/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a regular sequence of actions followed habitually",
                "definition_target": "日常规律；固定流程",
                "usage_pattern": "daily routine / study routine",
                "examples": [
                    {
                        "example_source": "A simple four-step listening routine removes decision fatigue.",
                        "example_target": "一套简洁的四步精听流程能消除每天学习的决策消耗。",
                    }
                ],
            }
        ],
    },
    "transform": {
        "headword": "transform",
        "category": "单词",
        "exam_tags": ["四级", "六级", "雅思"],
        "ipa_us": "/trænsˈfɔːrm/",
        "ipa_uk": "/trænsˈfɔːm/",
        "definitions": [
            {
                "pos": "verb",
                "definition_source": "to change the form, character, or effectiveness of something thoroughly",
                "definition_target": "彻底改变；转化；重塑",
                "usage_pattern": "transform A into B",
                "examples": [
                    {
                        "example_source": "Upload any clip to transform everyday media into an interactive study deck.",
                        "example_target": "上传任意片段，即可把日常影音转化为交互式精研讲义。",
                    }
                ],
            }
        ],
    },
    "retell": {
        "headword": "retell",
        "category": "单词",
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/ˌriːˈtɛl/",
        "ipa_uk": "/ˌriːˈtɛl/",
        "definitions": [
            {
                "pos": "verb",
                "definition_source": "to tell a story or explain an idea again in your own words",
                "definition_target": "用自己的话复述",
                "usage_pattern": "retell the story in your own words",
                "examples": [
                    {
                        "example_source": "Close the transcript and retell the main argument in three sentences.",
                        "example_target": "合上字幕，用三句话复述刚才的核心观点。",
                    }
                ],
            }
        ],
    },
    "habit": {
        "headword": "habit",
        "category": "单词",
        "exam_tags": ["四级"],
        "ipa_us": "/ˈhæbɪt/",
        "ipa_uk": "/ˈhæbɪt/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a settled or regular practice that becomes automatic through repetition",
                "definition_target": "习惯；惯常行为",
                "usage_pattern": "form / build a habit",
                "examples": [
                    {
                        "example_source": "Great listeners turn careful replay into an effortless daily habit.",
                        "example_target": "优秀的精听者会把仔细回听变成毫不费力的日常习惯。",
                    }
                ],
            }
        ],
    },
    "comprehension": {
        "headword": "comprehension",
        "category": "单词",
        "exam_tags": ["四级", "六级", "雅思"],
        "ipa_us": "/ˌkɑːmprɪˈhɛnʃən/",
        "ipa_uk": "/ˌkɒmprɪˈhɛnʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "the ability to understand spoken or written language accurately",
                "definition_target": "理解力；听力理解",
                "usage_pattern": "listening comprehension",
                "examples": [
                    {
                        "example_source": "Blind listening measures your real comprehension before subtitles step in.",
                        "example_target": "盲听能在字幕介入之前准确检验你真实的听力理解水平。",
                    }
                ],
            }
        ],
    },
    "expression": {
        "headword": "expression",
        "category": "单词",
        "exam_tags": ["四级", "口语"],
        "ipa_us": "/ɪkˈsprɛʃən/",
        "ipa_uk": "/ɪkˈsprɛʃən/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a particular word, phrase, or turn of speech used to convey a thought naturally",
                "definition_target": "表达方式；常用短语；神情",
                "usage_pattern": "idiomatic / useful expression",
                "examples": [
                    {
                        "example_source": "Star any useful expression to review it later in your personal deck.",
                        "example_target": "收藏任何实用的表达方式，方便后续在生词本中集中复习。",
                    }
                ],
            }
        ],
    },
    "master": {
        "headword": "master",
        "category": "单词",
        "exam_tags": ["四级", "雅思"],
        "ipa_us": "/ˈmæstər/",
        "ipa_uk": "/ˈmɑːstər/",
        "definitions": [
            {
                "pos": "verb",
                "definition_source": "to acquire complete skill, command, or deep familiarity with something",
                "definition_target": "精通；熟练掌握",
                "usage_pattern": "master + skill / phrase",
                "examples": [
                    {
                        "example_source": "Master one short scene deeply before moving on to the next episode.",
                        "example_target": "先把一个短场景彻底吃透，再进入下一集。",
                    }
                ],
            }
        ],
    },
    "insight": {
        "headword": "insight",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/ˈɪnsaɪt/",
        "ipa_uk": "/ˈɪnsaɪt/",
        "definitions": [
            {
                "pos": "noun",
                "definition_source": "a clear, deep understanding of a complex idea or pattern",
                "definition_target": "洞察；深刻理解",
                "usage_pattern": "gain insight into",
                "examples": [
                    {
                        "example_source": "Sentence analysis offers quick insight into how native clauses connect.",
                        "example_target": "句子精讲能让你迅速看清母语从句是如何衔接的。",
                    }
                ],
            }
        ],
    },
    "articulate": {
        "headword": "articulate",
        "category": "单词",
        "exam_tags": ["雅思", "托福", "考研"],
        "ipa_us": "/ɑːrˈtɪkjəleɪt/",
        "ipa_uk": "/ɑːˈtɪkjʊleɪt/",
        "definitions": [
            {
                "pos": "verb",
                "definition_source": "to express an idea or pronounce sounds clearly and distinctly",
                "definition_target": "清晰表达；咬字清楚地发出（音节）",
                "usage_pattern": "articulate + idea / sounds",
                "examples": [
                    {
                        "example_source": "Slowing the clip helps you articulate every final consonant cleanly.",
                        "example_target": "放慢片段倍速能帮助你把每个词尾辅音都清晰发出来。",
                    }
                ],
            }
        ],
    },
    "immerse": {
        "headword": "immerse",
        "category": "单词",
        "exam_tags": ["六级", "雅思", "托福"],
        "ipa_us": "/ɪˈmɜːrs/",
        "ipa_uk": "/ɪˈmɜːs/",
        "definitions": [
            {
                "pos": "verb",
                "definition_source": "to involve yourself deeply in an environment, language, or activity",
                "definition_target": "沉浸于；全身心投入",
                "usage_pattern": "immerse yourself in",
                "examples": [
                    {
                        "example_source": "Immerse yourself in topics you genuinely enjoy watching.",
                        "example_target": "让自己沉浸在真正喜欢看的主题内容中。",
                    }
                ],
            }
        ],
    },
    "capture": {
        "headword": "capture",
        "category": "单词",
        "exam_tags": ["四级", "六级"],
        "ipa_us": "/ˈkæptʃər/",
        "ipa_uk": "/ˈkæptʃər/",
        "definitions": [
            {
                "pos": "verb",
                "definition_source": "to record, preserve, or accurately represent a sound, idea, or moment",
                "definition_target": "捕捉；记录；准确再现",
                "usage_pattern": "capture + tone / detail / audio",
                "examples": [
                    {
                        "example_source": "Use a single click to capture your voice right alongside the transcript.",
                        "example_target": "一键即可在字幕旁录下你的跟读声音。",
                    }
                ],
            }
        ],
    },
}


def lemmatize_word(raw_word: str) -> str:
    w = re.sub(r"^[^a-zA-Z]+|[^a-zA-Z]+$", "", raw_word).lower()
    if not w:
        return ""
    if w in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[w]
    if w in CURATED_LEXICON:
        return w
    if len(w) > 4 and w.endswith("ies"):
        cand = w[:-3] + "y"
        if cand in CURATED_LEXICON:
            return cand
    if len(w) > 4 and w.endswith("ing"):
        for cand in (w[:-3], w[:-3] + "e", w[:-4] if len(w) > 5 and w[-4] == w[-5] else ""):
            if cand and cand in CURATED_LEXICON:
                return cand
    if len(w) > 3 and w.endswith("ed"):
        for cand in (w[:-2], w[:-1], w[:-3] if len(w) > 4 and w[-3] == w[-4] else ""):
            if cand and cand in CURATED_LEXICON:
                return cand
    if len(w) > 3 and w.endswith("es"):
        for cand in (w[:-2], w[:-1]):
            if cand in CURATED_LEXICON:
                return cand
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        cand = w[:-1]
        if cand in CURATED_LEXICON:
            return cand
    return w


def text_to_ipa(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    try:
        raw = ipa_lib.convert(cleaned)
        # Clean stray asterisks from OOV markers while preserving readability
        raw = raw.replace("*", "").strip()
        raw = re.sub(r"\s+", " ", raw)
        if raw and not raw.startswith("/"):
            return f"/{raw}/"
        return raw
    except Exception:
        return ""


def word_to_ipa(word: str) -> str:
    res = text_to_ipa(word)
    return res or f"/{word.lower()}/"


def estimate_word_timings(text: str, start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    tokens = [t for t in re.findall(r"[A-Za-z0-9'’-]+", text) if t]
    if not tokens:
        return []
    duration = max(0.2, end_sec - start_sec)
    weights = [max(1, len(re.sub(r"[^A-Za-z0-9]", "", tok))) for tok in tokens]
    total_w = sum(weights) or 1
    cursor = start_sec
    result = []
    for idx, (tok, w) in enumerate(zip(tokens, weights)):
        seg = duration * (w / total_w)
        w_start = round(cursor, 3)
        w_end = round(min(end_sec, cursor + seg), 3)
        cursor += seg
        result.append(
            {
                "index": idx,
                "word": tok,
                "start": w_start,
                "end": w_end,
                "has_timing": True,
            }
        )
    return result


def build_offline_entry(lemma: str, form: str, context_sentence: str = "") -> dict[str, Any]:
    key = lemma.lower().strip()
    if key in CURATED_LEXICON:
        base = CURATED_LEXICON[key]
        return {
            "headword": base["headword"],
            "lemma_key": key,
            "category": base["category"],
            "form": form,
            "exam_tags": list(base.get("exam_tags", [])),
            "pronunciations": [
                {"accent_type": "US", "ipa": base.get("ipa_us") or word_to_ipa(base["headword"]), "is_primary": True},
                {"accent_type": "UK", "ipa": base.get("ipa_uk") or word_to_ipa(base["headword"]), "is_primary": False},
            ],
            "definitions": base.get("definitions", []),
        }
    # Dynamic fallback entry for words not in curated lexicon
    ipa_val = word_to_ipa(key)
    pos_guess = "noun"
    if key.endswith("ly"):
        pos_guess = "adverb"
    elif key.endswith(("tion", "sion", "ment", "ness", "ity", "ence", "ance")):
        pos_guess = "noun"
    elif key.endswith(("ive", "ous", "ful", "less", "able", "ible", "al", "ic")):
        pos_guess = "adjective"
    elif key.endswith(("ize", "ise", "ate", "ify")):
        pos_guess = "verb"
    return {
        "headword": key,
        "lemma_key": key,
        "category": "单词",
        "form": form,
        "exam_tags": ["核心词"] if len(key) >= 7 else ["常用词"],
        "pronunciations": [
            {"accent_type": "US", "ipa": ipa_val, "is_primary": True},
            {"accent_type": "UK", "ipa": ipa_val, "is_primary": False},
        ],
        "definitions": [
            {
                "pos": pos_guess,
                "definition_source": f"Contextual vocabulary term extracted from the episode ({key}).",
                "definition_target": f"语境重点词「{key}」（配置 LLM API 或点击编辑可补充精准中文释义）",
                "usage_pattern": "",
                "examples": (
                    [{"example_source": context_sentence, "example_target": "（来自本片原句语境）"}]
                    if context_sentence
                    else []
                ),
            }
        ],
    }


BASIC_EVERYDAY_WORDS = {
    "every", "morning", "before", "after", "because", "small", "water", "fresh",
    "quiet", "street", "never", "simple", "daily", "short", "first", "without",
    "instead", "rather", "always", "other", "where", "which", "there", "their",
    "about", "would", "could", "should", "until", "through", "around", "between",
    "during", "since", "while", "under", "above", "below", "often", "years",
    "hours", "minutes", "words", "lines", "clips", "video", "audio", "mouth",
    "voice", "sound", "speed", "human", "world", "place", "house", "right",
    "great", "large", "young", "early", "least", "might", "seems", "begin",
    "start", "stops", "built", "gives", "keeps", "holds", "moves", "turns",
    "takes", "makes", "looks", "feels", "hears", "reads", "plays", "works",
    "lives", "needs", "wants", "means", "helps", "shows", "tries", "calls",
    "asked", "tells", "meets", "bring", "using", "doing", "being", "going",
    "having", "comes", "shuts", "treat", "meeting", "prepares", "prepare",
    "details", "detail", "grounds", "kettle", "steady", "feeling", "natural",
    "practice", "speaker", "speakers", "english", "sentence", "subtitles",
    "subtitle", "listen", "listening", "repeat", "phrase", "phrases", "lists",
    "study", "method", "approach", "training", "habits", "habit", "calm",
    "rushing", "motions", "tiniest", "ordinary", "craft", "genuine", "patience",
}


def extract_offline_candidates(subtitles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract high-value phrases & vocabulary offline across all subtitles without visual clutter."""
    found: dict[str, dict[str, Any]] = {}

    # 1. Scan for multi-word curated phrases first (highest learning value)
    for key, item in CURATED_LEXICON.items():
        if " " not in key:
            continue
        patterns = item.get("patterns") or [r"\b" + re.escape(key) + r"\b"]
        for sub in subtitles:
            txt = sub.get("source_text", "")
            for pat in patterns:
                m = re.search(pat, txt, flags=re.IGNORECASE)
                if m:
                    if key not in found:
                        found[key] = build_offline_entry(key, m.group(0), txt)
                    break

    # 2. Scan single content words (prefer curated words; keep extra fallback restrained)
    word_counts: dict[str, tuple[int, str, str]] = {}
    for sub in subtitles:
        txt = sub.get("source_text", "")
        for tok in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", txt):
            low = tok.lower().strip("'-")
            if not low or low in STOPWORDS or low in BASIC_EVERYDAY_WORDS:
                continue
            lemma = lemmatize_word(low)
            if not lemma or lemma in STOPWORDS or lemma in BASIC_EVERYDAY_WORDS or len(lemma) < 4:
                continue
            if lemma in CURATED_LEXICON:
                if lemma not in found:
                    found[lemma] = build_offline_entry(lemma, tok, txt)
            elif len(lemma) >= 7:
                cnt, sample_form, sample_ctx = word_counts.get(lemma, (0, tok, txt))
                word_counts[lemma] = (cnt + 1, sample_form, sample_ctx)

    # Keep total vocabulary focused and pedagogical (no noisy highlighting of every word)
    extra_budget = 3 if len(found) >= 8 else 14
    extra = sorted(
        word_counts.items(),
        key=lambda kv: (kv[1][0], len(kv[0])),
        reverse=True,
    )[:extra_budget]
    for lemma, (_cnt, sample_form, sample_ctx) in extra:
        if lemma not in found:
            found[lemma] = build_offline_entry(lemma, sample_form, sample_ctx)

    return list(found.values())


def annotate_subtitle_html(
    source_text: str,
    entry_records: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Match entries against source_text (longest phrase first, non-overlapping)
    and return (annotated_html, occurrences).
    """
    if not source_text:
        return "", []

    # Prepare candidate regexes ordered by headword length desc (phrases before single words)
    sorted_entries = sorted(
        entry_records,
        key=lambda e: len(e.get("headword", "")),
        reverse=True,
    )
    matches: list[tuple[int, int, dict[str, Any], str]] = []
    occupied = [False] * len(source_text)

    for entry in sorted_entries:
        headword = (entry.get("headword") or "").strip()
        if not headword:
            continue
        lemma_key = (entry.get("lemma_key") or headword).lower().strip()
        patterns: list[str] = []
        if lemma_key in CURATED_LEXICON and CURATED_LEXICON[lemma_key].get("patterns"):
            patterns.extend(CURATED_LEXICON[lemma_key]["patterns"])
        # Also include observed forms from the entry
        forms = set()
        if entry.get("form"):
            forms.add(entry["form"].strip())
        for f in entry.get("forms", []) or []:
            if f:
                forms.add(str(f).strip())
        forms.add(headword)
        if " " not in headword and re.match(r"^[A-Za-z]+$", headword):
            # Allow basic English inflections for single words
            base = re.escape(headword)
            patterns.append(rf"\b{base}(?:s|es|ed|d|ing|er|est)?\b")
            if headword.endswith("e") and len(headword) > 3:
                stem = re.escape(headword[:-1])
                patterns.append(rf"\b{stem}(?:ing|ed|es|er|est)\b")
            if headword.endswith("y") and len(headword) > 3:
                stem = re.escape(headword[:-1])
                patterns.append(rf"\b{stem}(?:ies|ied|ier|iest)\b")
        else:
            for f in sorted(forms, key=len, reverse=True):
                if f:
                    patterns.append(rf"\b{re.escape(f)}\b")

        for pat in patterns:
            try:
                for m in re.finditer(pat, source_text, flags=re.IGNORECASE):
                    s, e = m.start(), m.end()
                    if s >= e:
                        continue
                    if any(occupied[s:e]):
                        continue
                    for idx in range(s, e):
                        occupied[idx] = True
                    matches.append((s, e, entry, m.group(0)))
            except re.error:
                continue

    matches.sort(key=lambda x: x[0])
    parts: list[str] = []
    occurrences: list[dict[str, Any]] = []
    cursor = 0
    for s, e, entry, matched_text in matches:
        if s > cursor:
            parts.append(html.escape(source_text[cursor:s]))
        cat = entry.get("category", "单词")
        entry_id = entry["id"]
        parts.append(
            f'<span class="lex-term" data-entry-id="{entry_id}" data-category="{html.escape(cat)}" data-headword="{html.escape(entry["headword"])}">'
            f"{html.escape(matched_text)}</span>"
        )
        occurrences.append(
            {
                "entry_id": entry_id,
                "matched_form": matched_text,
                "char_start": s,
                "char_end": e,
            }
        )
        cursor = e
    if cursor < len(source_text):
        parts.append(html.escape(source_text[cursor:]))

    return "".join(parts), occurrences
