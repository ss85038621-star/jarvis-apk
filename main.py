# -*- coding: utf-8 -*-
# JARVIS - Android app (Kivy). Hindi voice assistant.
# सुनना: Android SpeechRecognizer (hi-IN) | बोलना: Android TextToSpeech | दिमाग: Gemini REST API
import json, os, re, ssl, threading, time, datetime, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()

ANDROID = platform == "android"
MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
GEM_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
IDLE_LIMIT = 15
DATA_DIR = "."

SYSTEM = (
    "तुम JARVIS हो, एक वॉइस असिस्टेंट। यूज़र हिंदी, अंग्रेज़ी या दोनों मिलाकर बोल सकता है। "
    "तुम्हें हमेशा सिर्फ़ हिंदी (देवनागरी) में जवाब देना है। जवाब छोटा रखो, एक-दो वाक्य। "
    "इमोजी, तारे या markdown मत लिखो, क्योंकि जवाब बोलकर सुनाया जाएगा। "
    "तुम फ़ोन के औज़ार (टॉर्च, वॉल्यूम, ऐप खोलना) खुद नहीं चला सकते; वे अलग से चलते हैं। "
    "ताज़ा ख़बर, मौसम या आज की घटनाएँ अपने मन से मत बनाओ; जो पता नहीं वह साफ़ कह दो।"
)

FONT = None
for _p in ["/system/fonts/NotoSansDevanagari-Regular.ttf", "/system/fonts/NotoSansDevanagariUI-Regular.ttf"]:
    if os.path.exists(_p):
        FONT = _p
        break
FKW = {"font_name": FONT} if FONT else {}

if ANDROID:
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread
    from android.permissions import request_permissions, check_permission, Permission

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Context = autoclass("android.content.Context")
    Intent = autoclass("android.content.Intent")
    IntentFilter = autoclass("android.content.IntentFilter")
    SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
    RecognizerIntent = autoclass("android.speech.RecognizerIntent")
    TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
    Locale = autoclass("java.util.Locale")

    class RecListener(PythonJavaClass):
        __javainterfaces__ = ["android/speech/RecognitionListener"]
        __javacontext__ = "app"

        def __init__(self, on_result, on_error, on_rms):
            super().__init__()
            self.on_result = on_result
            self.on_error = on_error
            self.on_rms = on_rms

        @java_method("(Landroid/os/Bundle;)V")
        def onReadyForSpeech(self, params):
            pass

        @java_method("()V")
        def onBeginningOfSpeech(self):
            pass

        @java_method("(F)V")
        def onRmsChanged(self, rms):
            self.on_rms(rms)

        @java_method("([B)V")
        def onBufferReceived(self, buf):
            pass

        @java_method("()V")
        def onEndOfSpeech(self):
            pass

        @java_method("(I)V")
        def onError(self, error):
            self.on_error(int(error))

        @java_method("(Landroid/os/Bundle;)V")
        def onResults(self, results):
            text = ""
            try:
                arr = results.getStringArrayList("results_recognition")
                if arr is not None and arr.size() > 0:
                    text = str(arr.get(0))
            except Exception:
                pass
            self.on_result(text)

        @java_method("(Landroid/os/Bundle;)V")
        def onPartialResults(self, partial):
            pass

        @java_method("(ILandroid/os/Bundle;)V")
        def onEvent(self, event_type, params):
            pass

    class TtsInit(PythonJavaClass):
        __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
        __javacontext__ = "app"

        def __init__(self, cb):
            super().__init__()
            self.cb = cb

        @java_method("(I)V")
        def onInit(self, status):
            self.cb(int(status))

    @run_on_ui_thread
    def ui_create_recognizer(holder, listener):
        holder["sr"] = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
        holder["sr"].setRecognitionListener(listener)

    @run_on_ui_thread
    def ui_start_listen(holder):
        sr = holder.get("sr")
        if sr is None:
            return
        i = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "hi-IN")
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "hi-IN")
        i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        sr.startListening(i)

    @run_on_ui_thread
    def ui_cancel_listen(holder):
        sr = holder.get("sr")
        if sr is not None:
            try:
                sr.cancel()
            except Exception:
                pass

    @run_on_ui_thread
    def ui_destroy_recognizer(holder):
        sr = holder.pop("sr", None)
        if sr is not None:
            try:
                sr.destroy()
            except Exception:
                pass


# ---------------- सेटिंग / याददाश्त की फ़ाइलें ----------------
def cfg_path():
    return os.path.join(DATA_DIR, "config.json")


def mem_path():
    return os.path.join(DATA_DIR, "memory.json")


def cfg_load():
    try:
        return json.load(open(cfg_path(), encoding="utf-8"))
    except Exception:
        return {}


def cfg_save(c):
    json.dump(c, open(cfg_path(), "w", encoding="utf-8"), ensure_ascii=False)


def mem_load():
    try:
        return json.load(open(mem_path(), encoding="utf-8"))
    except Exception:
        return []


def mem_save(items):
    json.dump(items, open(mem_path(), "w", encoding="utf-8"), ensure_ascii=False)


# ---------------- छोटे औज़ार ----------------
def has(t, words):
    return any(w in t for w in words)


HNUM = {"एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छ": 6, "सात": 7,
        "आठ": 8, "नौ": 9, "दस": 10, "पंद्रह": 15, "बीस": 20, "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60,
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}


def num_from(t):
    m = re.search(r"(\d+)", t)
    if m:
        return int(m.group(1))
    for w in t.split():
        if w in HNUM:
            return HNUM[w]
    return None


def http_get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JARVIS"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode("utf-8", "replace")


APPS = [
    (["बिज़नेस", "बिजनेस", "business"], "com.whatsapp.w4b", "व्हाट्सऐप बिज़नेस"),
    (["whatsapp", "whats app", "व्हाट्सऐप", "व्हाट्सएप", "वॉट्सऐप", "वाट्सऐप", "वाट्सएप", "व्हाट्स ऐप", "व्हाट्स अप"], "com.whatsapp", "व्हाट्सऐप"),
    (["youtube", "you tube", "यूट्यूब", "यू ट्यूब"], "com.google.android.youtube", "यूट्यूब"),
    (["chrome", "क्रोम"], "com.android.chrome", "क्रोम"),
    (["instagram", "इंस्टाग्राम"], "com.instagram.android", "इंस्टाग्राम"),
    (["facebook", "फेसबुक"], "com.facebook.katana", "फेसबुक"),
    (["telegram", "टेलीग्राम"], "org.telegram.messenger", "टेलीग्राम"),
    (["maps", "मैप", "गूगल मैप"], "com.google.android.apps.maps", "मैप्स"),
    (["gmail", "जीमेल"], "com.google.android.gm", "जीमेल"),
    (["spotify", "स्पोटिफाई"], "com.spotify.music", "स्पॉटिफ़ाई"),
    (["phonepe", "फोनपे", "फोन पे"], "com.phonepe.app", "फोनपे"),
    (["amazon", "अमेज़न", "अमेजन"], "in.amazon.mShop.android.shopping", "अमेज़न"),
]


class Ring(Widget):
    STATE_COL = {"STANDBY": (0.0, 0.6, 0.8), "LISTENING": (1.0, 0.25, 0.25),
                 "THINKING": (1.0, 0.7, 0.0), "SPEAKING": (0.1, 0.9, 0.5)}
    SPEED = {"STANDBY": 20, "LISTENING": 70, "THINKING": 200, "SPEAKING": 100}

    def __init__(self, **kw):
        super().__init__(**kw)
        self.state = "STANDBY"
        self.t = 0.0
        self.level = 0.0
        Clock.schedule_interval(self.tick, 1 / 30.0)

    def tick(self, dt):
        self.t += dt * self.SPEED.get(self.state, 20)
        self.level *= 0.9
        cx, cy = self.center
        r = min(self.width, self.height) / 2.0 * 0.85
        col = self.STATE_COL.get(self.state, (0, 0.6, 0.8))
        self.canvas.clear()
        with self.canvas:
            Color(col[0], col[1], col[2], 0.25)
            Line(circle=(cx, cy, r), width=1.5)
            Color(col[0], col[1], col[2], 0.9)
            Line(circle=(cx, cy, r * (0.35 + 0.15 * self.level)), width=2.5)
            for i, (rad, wid, off) in enumerate([(0.92, 3, 0), (0.76, 2.5, 120), (0.6, 2, 240)]):
                a = self.t * (1 + i * 0.5) * (1 if i % 2 == 0 else -1) + off
                Line(circle=(cx, cy, r * rad, a, a + 100), width=wid)


class JarvisApp(App):
    def build(self):
        global DATA_DIR
        DATA_DIR = self.user_data_dir
        self.title = "JARVIS"
        Window.clearcolor = (0.0, 0.04, 0.06, 1.0)
        self.active = False
        self.history = []
        self.undo = []
        self.holder = {}
        self.tts = None
        self.tts_ready = False
        self.tts_cb = None
        self.err_count = 0
        self.last_heard = time.time()
        self.torch_on = False
        self.lines = []

        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        self.status = Label(text="STANDBY", size_hint_y=None, height=36, color=(0.3, 0.9, 1, 1), font_size=20)
        self.ring = Ring(size_hint_y=0.42)
        self.log_lbl = Label(text="", size_hint_y=None, halign="left", valign="top",
                             color=(0.85, 0.95, 1, 1), font_size=16, **FKW)
        self.log_lbl.bind(width=lambda *a: setattr(self.log_lbl, "text_size", (self.log_lbl.width, None)),
                          texture_size=lambda *a: setattr(self.log_lbl, "height", self.log_lbl.texture_size[1]))
        self.sv = ScrollView(size_hint_y=0.4)
        self.sv.add_widget(self.log_lbl)
        self.btn = Button(text="START", size_hint_y=None, height=90, font_size=26,
                          background_color=(0.0, 0.5, 0.7, 1))
        self.btn.bind(on_release=self.toggle)
        sb = Button(text="SETTINGS", size_hint_y=None, height=50, background_color=(0.2, 0.2, 0.25, 1))
        sb.bind(on_release=lambda *a: self.open_settings())
        for w in (self.status, self.ring, self.sv, self.btn, sb):
            root.add_widget(w)
        return root

    def on_start(self):
        if ANDROID:
            try:
                request_permissions([Permission.RECORD_AUDIO])
            except Exception:
                pass
            self.listener = RecListener(
                lambda txt: Clock.schedule_once(lambda dt: self.on_result(txt), 0),
                lambda code: Clock.schedule_once(lambda dt: self.on_error(code), 0),
                self.on_rms)
            ui_create_recognizer(self.holder, self.listener)
            self.tts_listener = TtsInit(lambda st: Clock.schedule_once(lambda dt: self.on_tts_init(st), 0))
            self.tts = TextToSpeech(PythonActivity.mActivity, self.tts_listener)
        if not cfg_load().get("key"):
            Clock.schedule_once(lambda dt: self.open_settings(), 1.0)
        self.log("तैयार। START दबाइए।")

    def on_pause(self):
        return True

    def on_resume(self):
        pass

    # ---------- UI ----------
    def set_state(self, s):
        self.ring.state = s
        self.status.text = s

    def log(self, text):
        self.lines.append(text)
        self.lines = self.lines[-30:]
        self.log_lbl.text = "\n".join(self.lines)
        Clock.schedule_once(lambda dt: setattr(self.sv, "scroll_y", 0), 0.1)

    def open_settings(self):
        c = cfg_load()
        box = BoxLayout(orientation="vertical", padding=10, spacing=10)
        key_in = TextInput(hint_text="Gemini API key", text=c.get("key", ""), password=True,
                           multiline=False, size_hint_y=None, height=60)
        city_in = TextInput(hint_text="City (मौसम के लिए), e.g. Delhi", text=c.get("city", "Delhi"),
                            multiline=False, size_hint_y=None, height=60)
        save = Button(text="SAVE", size_hint_y=None, height=70)
        pop = Popup(title="Settings", content=box, size_hint=(0.92, 0.5))

        def _save(*a):
            cfg_save({"key": key_in.text.strip(), "city": city_in.text.strip() or "Delhi"})
            pop.dismiss()
            self.log("सेटिंग सेव हो गई।")

        save.bind(on_release=_save)
        for w in (key_in, city_in, save):
            box.add_widget(w)
        pop.open()

    # ---------- बोलना ----------
    def on_tts_init(self, status):
        if status != 0:
            self.log("TTS शुरू नहीं हो पाया।")
            return
        try:
            res = self.tts.setLanguage(Locale("hi", "IN"))
            if int(res) < 0:
                self.log("हिंदी आवाज़ नहीं मिली। फ़ोन सेटिंग में Google TTS की हिंदी आवाज़ डाउनलोड करें।")
        except Exception as e:
            self.log("TTS भाषा त्रुटि: " + str(e)[:60])
        self.tts_ready = True

    def speak_raw(self, text):
        if not (ANDROID and self.tts_ready):
            return
        try:
            self.tts.speak(text, 0, None, "jarvis")
        except Exception as e:
            self.log("बोल नहीं पाया: " + str(e)[:60])

    def tts_busy(self):
        try:
            return bool(self.tts.isSpeaking())
        except Exception:
            return False

    def say(self, text, listen_after=True):
        text = re.sub(r"[*#_`>]+", "", text).strip()
        self.log("JARVIS: " + text)
        self.set_state("SPEAKING")
        self.speak_raw(text)
        self._listen_after = listen_after
        self._poll_start = time.time()
        Clock.unschedule(self._poll)
        Clock.schedule_once(lambda dt: Clock.schedule_interval(self._poll, 0.3), 0.8)

    def _poll(self, dt):
        if self.tts_busy() and time.time() - self._poll_start < 90:
            return True
        if self._listen_after and self.active:
            Clock.schedule_once(lambda d: self.listen(), 0.5)
        else:
            self.set_state("STANDBY")
        return False

    # ---------- सुनना ----------
    def toggle(self, *a):
        if self.active:
            self.stop_session()
        else:
            self.start_session()

    def start_session(self):
        if ANDROID and not check_permission(Permission.RECORD_AUDIO):
            request_permissions([Permission.RECORD_AUDIO])
            self.log("माइक की इजाज़त दीजिए, फिर दोबारा START दबाइए।")
            return
        if not cfg_load().get("key"):
            self.open_settings()
            return
        self.active = True
        self.err_count = 0
        self.last_heard = time.time()
        self.btn.text = "STOP"
        self.say("नमस्ते सर, मैं जार्विस हूँ। बोलिए।")

    def stop_session(self, goodbye=None):
        self.active = False
        self.btn.text = "START"
        Clock.unschedule(self._poll)
        if ANDROID:
            ui_cancel_listen(self.holder)
        if goodbye:
            self.say(goodbye, listen_after=False)
        else:
            self.set_state("STANDBY")

    def listen(self):
        if not self.active:
            return
        self.set_state("LISTENING")
        if ANDROID:
            ui_start_listen(self.holder)

    def on_rms(self, rms):
        try:
            self.ring.level = max(0.0, min(1.0, (float(rms) + 2.0) / 12.0))
        except Exception:
            pass

    def on_error(self, code):
        if not self.active:
            return
        if time.time() - self.last_heard > IDLE_LIMIT:
            self.stop_session("ठीक है सर, मैं बंद हो रहा हूँ।")
            return
        self.err_count += 1
        if code == 9:
            self.log("माइक की इजाज़त नहीं है।")
            self.stop_session()
            return
        if self.err_count > 12:
            self.log("सुनने में बार-बार दिक्कत (कोड %d)। रुक रहा हूँ।" % code)
            self.stop_session()
            return
        if code in (5, 8, 3):
            if ANDROID:
                ui_destroy_recognizer(self.holder)
                Clock.schedule_once(lambda dt: ui_create_recognizer(self.holder, self.listener), 0.5)
            Clock.schedule_once(lambda dt: self.listen(), 1.5)
        else:
            Clock.schedule_once(lambda dt: self.listen(), 0.4)

    def on_result(self, text):
        if not self.active:
            return
        text = (text or "").strip()
        if not text:
            self.on_error(7)
            return
        self.err_count = 0
        self.last_heard = time.time()
        self.log("आप: " + text)
        t = " " + text.lower() + " "
        guard = ["torch", "टॉर्च", "टार्च", "wifi", "वाईफाई", "volume", "वॉल्यूम", "वोल्यूम"]
        if (has(t, ["अलविदा", "alvida", "goodbye", "good bye", "बंद हो जाओ", "band ho jao", "band ho ja", "बंद करो जार्विस",
                    "band karo jarvis", "jarvis band", "जार्विस बंद", "exit"])
                or (has(t, ["बंद", "band"]) and has(t, ["जार", "jar", "हो जा", "ho ja", "ठीक है", "theek", "thik"]))) \
                and not has(t, guard):
            self.stop_session("ठीक है सर, अलविदा।")
            return
        self.set_state("THINKING")
        threading.Thread(target=self.work, args=(text, t), daemon=True).start()

    def work(self, text, t):
        try:
            ans = self.handle(text, t)
        except Exception as e:
            ans = "माफ़ कीजिए, कुछ गड़बड़ हो गई।"
            print("ERR handle:", e)
        Clock.schedule_once(lambda dt: self.say(ans), 0)

    # ---------- कमांड ----------
    def handle(self, s, t):
        for h in (self.c_undo, self.c_memory, self.c_reminder, self.c_alarm, self.c_volume, self.c_torch,
                  self.c_battery, self.c_weather, self.c_news, self.c_time, self.c_apps, self.c_unsupported, self.c_help):
            try:
                r = h(s, t)
            except Exception as e:
                print("ERR", h.__name__, e)
                r = None
            if r:
                return r
        return self.gemini(s)

    def c_help(self, s, t):
        if not has(t, ["क्या कर सकते", "kya kar sakte", "help", "मदद", "madad"]):
            return None
        return ("मैं ये कर सकता हूँ: बातचीत, याद रखना, मौसम, ख़बरें, समय, टॉर्च, बैटरी, वॉल्यूम, "
                "रिमाइंडर, अलार्म, ऐप खोलना, और वापस करना।")

    def c_unsupported(self, s, t):
        if has(t, ["wifi", "वाईफाई", "वाई-फाई", "वाई फाई", "brightness", "ब्राइटनेस", "sms", "एसएमएस"]):
            return "यह काम अभी ऐप में उपलब्ध नहीं है।"
        return None

    def c_undo(self, s, t):
        if not has(t, ["undo", "अनडू", "वापस करो", "wapas karo", "पिछला काम"]):
            return None
        if not self.undo:
            return "वापस करने लायक कोई काम नहीं है।"
        name, fn = self.undo.pop()
        try:
            fn()
            return name + " वाला काम वापस कर दिया।"
        except Exception:
            return "वापस नहीं कर पाया।"

    def c_memory(self, s, t):
        if has(t, ["क्या याद है", "kya yaad hai", "याददाश्त दिखा", "what do you remember"]):
            items = mem_load()
            return ("मुझे ये याद है: " + "। ".join(items[-8:])) if items else "मुझे अभी कुछ याद नहीं है।"
        if has(t, ["सब भूल", "sab bhul", "forget everything", "याददाश्त मिटा"]):
            mem_save([])
            return "मैंने सब भुला दिया।"
        q = has(t, ["क्या", "kya", "?", "बताओ", "batao", "कौन", "kaun"])
        if not q:
            if has(t, ["याद रख", "yaad rakh", "yad rakh", "remember"]) or \
               (has(t, ["मेरा नाम", "mera naam", "my name"]) and has(t, [" है", " hai", " is "])):
                items = mem_load()
                items.append(s)
                mem_save(items)
                return "ठीक है, याद रख लिया।"
        return None

    def c_time(self, s, t):
        if not has(t, ["कितने बजे", "kitne baje", "बज रहे", "baj rahe", "समय क्या", "time kya", "what time", "तारीख",
                       "tarikh", "date kya", "आज कौन सा दिन", "क्या टाइम", "टाइम क्या"]):
            return None
        n = datetime.datetime.now()
        mnth = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"][n.month - 1]
        return "अभी %d बजकर %d मिनट हुए हैं। आज %d %s %d है।" % (n.hour % 12 or 12, n.minute, n.day, mnth, n.year)

    # टॉर्च
    def set_torch(self, on):
        cm = PythonActivity.mActivity.getSystemService(Context.CAMERA_SERVICE)
        ids = cm.getCameraIdList()
        last = None
        for cid in ids:
            try:
                cm.setTorchMode(cid, bool(on))
                self.torch_on = bool(on)
                return True
            except Exception as e:
                last = e
        raise last or Exception("no camera")

    def c_torch(self, s, t):
        if not has(t, ["टॉर्च", "torch", "flashlight", "टार्च", "फ्लैशलाइट", "tourch", "फ़्लैशलाइट"]):
            return None
        if not ANDROID:
            return "यह फ़ोन पर ही चलेगा।"
        off = has(t, ["बंद", "band", " off", "बुझा", "bujha"])
        try:
            self.set_torch(not off)
        except Exception as e:
            return "टॉर्च नहीं चल पाई।"
        self.undo.append(("टॉर्च", lambda: self.set_torch(off)))
        return "टॉर्च बंद कर दी।" if off else "टॉर्च चालू कर दी।"

    def c_battery(self, s, t):
        if not has(t, ["बैटरी", "battery", "बैटरि", "बेटरी"]):
            return None
        if not ANDROID:
            return None
        st = PythonActivity.mActivity.registerReceiver(None, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        level = st.getIntExtra("level", -1)
        scale = st.getIntExtra("scale", 100)
        status = st.getIntExtra("status", -1)
        pct = int(level * 100 / scale) if level >= 0 else -1
        if pct < 0:
            return "बैटरी की जानकारी नहीं मिल पाई।"
        extra = " और चार्ज हो रही है।" if status in (2, 5) else "।"
        return "बैटरी %d प्रतिशत है%s" % (pct, extra)

    def c_volume(self, s, t):
        up = has(t, ["बढ़ा", "badha", "increase", "ज़्यादा", "zyada", "तेज़", "tez", "तेज", " up"])
        down = has(t, ["कम", "kam", "घटा", "ghata", "decrease", "down", "धीरे", "dheere"])
        named = has(t, ["वॉल्यूम", "volume", "वोल्यूम", "वॉल्युम"])
        if not (named or (has(t, ["आवाज़", "आवाज", "awaaz", "awaz"]) and (up or down))):
            return None
        if not ANDROID:
            return None
        am = PythonActivity.mActivity.getSystemService(Context.AUDIO_SERVICE)
        cur = am.getStreamVolume(3)
        mx = am.getStreamMaxVolume(3)
        step = max(1, round(mx * 0.15))
        n = num_from(t)
        if has(t, ["म्यूट", "mute"]):
            new = 0
        elif has(t, ["फुल", "full", "पूरा", "max"]):
            new = mx
        elif n is not None and has(t, ["percent", "प्रतिशत", "%", "परसेंट", "पर्सेंट"]):
            new = round(n * mx / 100.0)
        elif n is not None and not up and not down:
            new = n
        elif up:
            new = cur + step
        elif down:
            new = cur - step
        else:
            return "वॉल्यूम अभी %d है, अधिकतम %d।" % (cur, mx)
        new = max(0, min(mx, new))
        am.setStreamVolume(3, new, 1)
        self.undo.append(("वॉल्यूम", lambda: am.setStreamVolume(3, cur, 1)))
        return "वॉल्यूम %d कर दिया।" % new

    # मौसम / ख़बरें
    def c_weather(self, s, t):
        if not has(t, ["मौसम", "mausam", "weather", "मौसाम"]):
            return None
        skip = ["aaj", "आज", "abhi", "अभी", "jarvis", "जार्विस", "ye", "yeh", "ka", "ki", "का", "की", "के", "ke", "mausam",
                "मौसम", "kya", "क्या", "kaisa", "कैसा", "hai", "है", "batao", "बताओ", "bata", "बता", "do", "दो", "mein", "में",
                "in", "weather", "the", "of", "रहा", "रहेगा", "हाल"]
        parts = t.split()
        found = None
        for k, w in enumerate(parts):
            if w in ["mein", "में", "in"]:
                if k > 0 and parts[k - 1] not in skip:
                    found = parts[k - 1]
                    break
                if k + 1 < len(parts) and parts[k + 1] not in skip:
                    found = parts[k + 1]
                    break
        if not found:
            for k, w in enumerate(parts):
                if w in ["ka", "का", "ki", "की", "ke", "के"] and k > 0 and parts[k - 1] not in skip:
                    found = parts[k - 1]
                    break
        city = found or cfg_load().get("city") or "Delhi"
        try:
            out = http_get("https://wttr.in/" + urllib.parse.quote(city) + "?format=%t+%h+%C&lang=hi").strip()
        except Exception:
            return "मौसम की जानकारी नहीं मिल पाई।"
        if not out or "Unknown" in out:
            return "मौसम की जानकारी नहीं मिल पाई।"
        return city + " में अभी मौसम: " + out

    def news_titles(self, n=4):
        try:
            xml = http_get("https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi", 12)
            root = ET.fromstring(xml)
            out = []
            for it in root.iter("item"):
                title = re.sub(r"\s+-\s+[^-]+$", "", it.findtext("title") or "")
                if title:
                    out.append(title)
                if len(out) >= n:
                    break
            return out
        except Exception:
            return []

    def c_news(self, s, t):
        if not has(t, ["खबर", "ख़बर", "khabar", "khabr", "news", "समाचार", "न्यूज", "headline"]):
            return None
        tl = self.news_titles(4)
        if not tl:
            return "ख़बरें नहीं मिल पाईं।"
        return "आज की मुख्य ख़बरें। " + "। ".join(tl)

    # रिमाइंडर / अलार्म
    def c_reminder(self, s, t):
        m = re.search(r"(second|sec|सेकंड|सेकेंड|मिनट|minute|min|घंटे|घंटा|ghant|hour)", t)
        if not (m and has(t, ["याद दिला", "yaad dila", "yad dila", "remind", "रिमाइंडर", "बाद", "baad", "bad ", "timer", "टाइमर"])):
            return None
        n = num_from(t)
        if n is None:
            return "कितने समय बाद? जैसे, दस मिनट बाद याद दिलाना।"
        u = m.group(1)
        if u in ["second", "sec", "सेकंड", "सेकेंड"]:
            mult, name = 1, "सेकंड"
        elif u in ["मिनट", "minute", "min"]:
            mult, name = 60, "मिनट"
        else:
            mult, name = 3600, "घंटे"
        msg = "सर, रिमाइंडर। " + s

        def fire():
            self.speak_raw(msg)
            Clock.schedule_once(lambda dt: self.log("रिमाइंडर: " + s), 0)

        tm = threading.Timer(n * mult, fire)
        tm.daemon = True
        tm.start()
        return "ठीक है, %d %s बाद याद दिलाऊँगा। इस बीच ऐप बंद मत कीजिए।" % (n, name)

    def c_alarm(self, s, t):
        if not has(t, ["अलार्म", "alarm"]):
            return None
        m = re.search(r"(\d{1,2})(?::(\d{2}))? *(बजे|baje|bje)", t)
        if not m:
            n = num_from(t)
            if n is None or n > 12:
                return "कितने बजे का अलार्म लगाना है? जैसे, सुबह छह बजे का अलार्म।"
            h, mi = n, 0
        else:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
        if has(t, ["शाम", "shaam", "रात", "raat", "दोपहर", "dopahar", " pm"]) and h < 12:
            h += 12
        i = Intent("android.intent.action.SET_ALARM")
        i.putExtra("android.intent.extra.alarm.HOUR", h)
        i.putExtra("android.intent.extra.alarm.MINUTES", mi)
        i.putExtra("android.intent.extra.alarm.SKIP_UI", True)
        i.addFlags(0x10000000)
        PythonActivity.mActivity.startActivity(i)
        return "अलार्म %d बजकर %d मिनट पर लगा दिया।" % (h % 12 or 12, mi)

    # ऐप खोलना
    def c_apps(self, s, t):
        verb = has(t, ["खोल", "kholo", "khol", "open", "चालू", "chalu", "start", "लगा", "चलाओ"])
        short = len(t.split()) <= 2
        if has(t, ["settings", "सेटिंग"]) and verb:
            i = Intent("android.settings.SETTINGS")
            i.addFlags(0x10000000)
            PythonActivity.mActivity.startActivity(i)
            return "सेटिंग्स खोल रहा हूँ।"
        if has(t, ["camera", "कैमरा"]) and verb:
            i = Intent("android.media.action.STILL_IMAGE_CAMERA")
            i.addFlags(0x10000000)
            PythonActivity.mActivity.startActivity(i)
            return "कैमरा खोल रहा हूँ।"
        if not (verb or short):
            return None
        for names, pkg, label in APPS:
            if has(t, names):
                pm = PythonActivity.mActivity.getPackageManager()
                i = pm.getLaunchIntentForPackage(pkg)
                if i is None:
                    return label + " फ़ोन में नहीं मिला।"
                i.addFlags(0x10000000)
                PythonActivity.mActivity.startActivity(i)
                return label + " खोल रहा हूँ।"
        return None

    # Gemini
    def gemini(self, text):
        key = cfg_load().get("key", "")
        if not key:
            return "पहले सेटिंग में API key डालिए।"
        self.history.append({"role": "user", "parts": [{"text": text}]})
        self.history = self.history[-20:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)
        mem = " | ".join(mem_load()[-30:])
        body = {"system_instruction": {"parts": [{"text": SYSTEM + " यूज़र के बारे में याद रखी बातें: " + mem}]},
                "contents": self.history}
        for m in MODELS:
            try:
                req = urllib.request.Request(GEM_URL.format(m), data=json.dumps(body).encode("utf-8"),
                                             headers={"Content-Type": "application/json", "x-goog-api-key": key})
                with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                    data = json.load(r)
                ans = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                self.history.append({"role": "model", "parts": [{"text": ans}]})
                return ans
            except urllib.error.HTTPError as e:
                print("ERR", m, e.code)
            except Exception as e:
                print("ERR", m, str(e)[:100])
        self.history.pop()
        return "माफ़ कीजिए, अभी जवाब नहीं मिल पाया।"


if __name__ == "__main__":
    JarvisApp().run()
