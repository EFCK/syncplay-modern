# coding:utf8
from syncplay import constants

from . import messages_de
from . import messages_en
from . import messages_es
from . import messages_eo
from . import messages_fi
from . import messages_fr
from . import messages_it
from . import messages_pt_PT
from . import messages_pt_BR
from . import messages_tr
from . import messages_ru
from . import messages_zh_CN
from . import messages_ko
import re

# In alphabetical order
messages = {
    "de": messages_de.de,
    "en": messages_en.en,
    "es": messages_es.es,
    "eo": messages_eo.eo,
    "fi": messages_fi.fi,
    "fr": messages_fr.fr,
    "it": messages_it.it,
    "pt_PT": messages_pt_PT.pt_PT,
    "pt_BR": messages_pt_BR.pt_BR,
    "tr": messages_tr.tr,
    "ru": messages_ru.ru,
    "zh_CN": messages_zh_CN.zh_CN,
     "ko": messages_ko.ko,
    "CURRENT": None
}

no_osd_message_list = [
    "slowdown-notification",
    "revert-notification",
]

def getLanguages():
    langList = {}
    for lang in messages:
        if lang != "CURRENT":
            langList[lang] = getMessage("LANGUAGE", lang)
    return langList

def getLanguageTags():
    langList = {}
    for lang in messages:
        if lang != "CURRENT":
            langList[lang] = getMessage("LANGUAGE-TAG", lang)
    return langList

def isNoOSDMessage(message):
    for no_osd_message in no_osd_message_list:
        regex = "^" + getMessage(no_osd_message).replace("{}", ".+") + "$"
        regex_test = bool(re.match(regex, message))
        if regex_test:
            return True
    return False

def setLanguage(lang):
    messages["CURRENT"] = lang

def getMissingStrings():
    missingStrings = ""
    for lang in messages:
        if lang != "en" and lang != "CURRENT":
            for message in messages["en"]:
                if message not in messages[lang]:
                    missingStrings = missingStrings + "({}) Missing: {}\n".format(lang, message)
            for message in messages[lang]:
                if message not in messages["en"]:
                    missingStrings = missingStrings + "({}) Unused: {}\n".format(lang, message)

    return missingStrings


def _detect_os_locale_code():
    """Return a locale-code string for the OS (e.g. ``"pt_PT"``), or ``""``.

    Prefers the modern, non-deprecated APIs. Order:
    1. Frozen macOS app → Qt's ``QLocale.system().uiLanguages()`` (matches
       the user's System Settings choice rather than POSIX env vars,
       which py2app bundles often leave unset).
    2. POSIX env vars (``LC_ALL`` / ``LC_MESSAGES`` / ``LANG``) — most
       reliable on Linux, also honoured by macOS Terminal sessions.
    3. ``locale.getlocale()`` — what the deprecated
       ``locale.getdefaultlocale()`` was rewritten to defer to.
    """
    import sys
    frozen = getattr(sys, 'frozen', '')
    if frozen and frozen in 'macosx_app':
        # Prefer PySide6 (the modern fork's GUI binding); fall back to
        # PySide2 so this still works in any pre-fork environment that
        # only has PySide2 available.
        try:
            from PySide6.QtCore import QLocale  # type: ignore
        except ImportError:
            from PySide2.QtCore import QLocale  # type: ignore
        try:
            tags = QLocale.system().uiLanguages()
            if tags:
                return tags[0].replace('-', '_')
        except Exception:
            pass

    import os
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        raw = os.environ.get(var)
        if raw and raw not in ('C', 'POSIX'):
            return raw.split('.')[0].split('@')[0]

    try:
        import locale
        code, _enc = locale.getlocale()
        if code:
            return code
    except (TypeError, ValueError):
        pass
    return ""


def getInitialLanguage():
    """Pick a language code present in ``messages`` based on the OS.

    Tries the full code first (so ``pt_PT`` stays Portuguese-Portugal
    rather than collapsing to ``pt`` and missing the table); falls back
    to the language-only prefix; finally falls back to the project's
    configured default.
    """
    try:
        raw = _detect_os_locale_code()
        if raw:
            full = raw.replace('-', '_')
            if full in messages:
                return full
            short = full.split('_')[0]
            if short in messages:
                return short
    except Exception:
        pass
    return constants.FALLBACK_INITIAL_LANGUAGE


def isValidLanguage(language):
    return language in messages


def getMessage(type_, locale=None):
    if constants.SHOW_TOOLTIPS == False:
        if "-tooltip" in type_:
            return ""

    if not isValidLanguage(messages["CURRENT"]):
        setLanguage(getInitialLanguage())

    lang = messages["CURRENT"]
    if locale and locale in messages:
        if type_ in messages[locale]:
            return str(messages[locale][type_])
    if lang and lang in messages:
        if type_ in messages[lang]:
            return str(messages[lang][type_])
    if type_ in messages["en"]:
        return str(messages["en"][type_])
    else:
        print("WARNING: Cannot find message '{}'!".format(type_))
        #return "!{}".format(type_)  # TODO: Remove
        raise KeyError(type_)

def populateLanguageArgument():
    languageTags = "/".join(getLanguageTags())
    langList = {}
    for lang in messages:
        if lang != "CURRENT":
            messages[lang]["language-argument"] = messages[lang]["language-argument"].format(languageTags)
    return langList

populateLanguageArgument()
