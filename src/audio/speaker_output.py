"""Voice Module- Deprecated """
import pyttsx3

engine = pyttsx3.init()
voices = engine.getProperty("voices")

engine.setProperty("rate", 180)
engine.setProperty("volume", 1.0)
engine.setProperty("voice", voices[1].id)

def speak(texto):
    """Voice Function """
    engine.say(texto)
    engine.runAndWait()
