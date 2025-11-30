"""
Advanced Voice Assistant using Vosk (offline speech recognition)
Features:
 - Offline speech recognition (Vosk + sounddevice)
 - Text-to-speech (pyttsx3)
 - Weather (OpenWeatherMap API)
 - Wikipedia queries
 - Send email (SMTP) - optional, needs credentials
 - Reminders (local, threaded)
 - Persistent custom commands (JSON)
 - Fallback to text input if recognition fails
"""

import os
import json
import time
import threading
import requests
import wikipedia
import smtplib
import queue
import sys

import pyttsx3
import sounddevice as sd
from vosk import Model, KaldiRecognizer

# ---------------- CONFIG ----------------
# Path to the extracted VOSK model folder (must exist)
VOSK_MODEL_PATH = "vosk-model-small-en-us-0.15"

# OpenWeather API key (replace with your own)
OPENWEATHER_API_KEY = "YOUR_OPENWEATHER_API_KEY_HERE"

# Email credentials (optional; use app password for Gmail)
EMAIL_ADDRESS = "YOUR_EMAIL@gmail.com"
EMAIL_PASSWORD = "YOUR_APP_PASSWORD_HERE"

# Custom commands file
CUSTOM_COMMANDS_FILE = "custom_commands.json"

# Sample default city for weather (used if user doesn't provide city)
DEFAULT_CITY = "Chennai"

# ----------------- INIT ------------------
def speak(text):
    """Speak text reliably and print it."""
    print("\nAssistant:", text)
    engine = pyttsx3.init()
    engine.setProperty("rate", 160)
    engine.say(text)
    engine.runAndWait()

# Load custom commands (persistent)
if os.path.exists(CUSTOM_COMMANDS_FILE):
    try:
        with open(CUSTOM_COMMANDS_FILE, "r", encoding="utf-8") as f:
            custom_commands = json.load(f)
    except Exception:
        custom_commands = {}
else:
    custom_commands = {}

def save_custom_commands():
    try:
        with open(CUSTOM_COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(custom_commands, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to save custom commands:", e)

# ---------------- VOSK LISTENING ----------------
if not os.path.exists(VOSK_MODEL_PATH):
    speak(f"Vosk model folder not found at '{VOSK_MODEL_PATH}'. Please place the extracted model in the same directory.")
    sys.exit(1)

model = Model(VOSK_MODEL_PATH)
q = queue.Queue()

def sd_callback(indata, frames, time_info, status):
    if status:
        print("Sounddevice status:", status, file=sys.stderr)
    q.put(bytes(indata))

def listen_vosk(timeout=None):
    rec = KaldiRecognizer(model, 16000)
    speak("Listening now.")
    try:
        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                               channels=1, callback=sd_callback):
            start_time = time.time()
            while True:
                data = q.get()
                if rec.AcceptWaveform(data):
                    res = rec.Result()
                    try:
                        j = json.loads(res)
                        text = j.get("text", "").strip().lower()
                    except Exception:
                        text = ""
                    if text:
                        print("You said:", text)
                        return text
                if timeout and (time.time() - start_time) > timeout:
                    break
    except Exception as e:
        print("Microphone / sounddevice error:", e)
    speak("I couldn't hear clearly. Please type your command:")
    typed = input("Type your command: ").strip().lower()
    return typed

# ----------------- TASK FUNCTIONS -----------------
def get_weather(city):
    if not OPENWEATHER_API_KEY:
        speak("Weather API key not set.")
        return
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=10)
        data = r.json()
        if r.status_code != 200:
            speak(f"Could not fetch weather for {city}. {data.get('message','')}")
            return
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        speak(f"In {city}, the temperature is {round(temp)}°C with {desc}.")
    except Exception as e:
        print("Weather error:", e)
        speak("Sorry, I couldn't get the weather right now.")

def send_email(to_address, subject, message):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        speak("Email credentials are not set. Please configure them in the script.")
        return
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        body = f"Subject: {subject}\n\n{message}"
        server.sendmail(EMAIL_ADDRESS, to_address, body)
        server.quit()
        speak("Email sent successfully.")
    except Exception as e:
        print("Email error:", e)
        speak("Failed to send the email. Check credentials or network.")

def set_reminder(text, minutes):
    def worker():
        time.sleep(max(0, minutes) * 60)
        speak(f"Reminder: {text}")
    threading.Thread(target=worker, daemon=True).start()
    speak(f"Reminder set for {minutes} minutes from now.")

def answer_wikipedia(query):
    try:
        summary = wikipedia.summary(query, sentences=2, auto_suggest=True, redirect=True)
        speak(summary)
    except Exception as e:
        print("Wikipedia error:", e)
        speak("I couldn't find a Wikipedia answer for that.")

# ----------------- NLP / PROCESS COMMAND -----------------
def process_command(command):
    if not command:
        return

    if any(word in command for word in ["exit", "quit", "stop", "bye"]):
        speak("Goodbye. Exiting now.")
        sys.exit(0)

    if command in custom_commands:
        speak(custom_commands[command])
        return

    if any(g in command for g in ["hello", "hi", "hey"]):
        speak("Hello! How can I help you?")
        return

    if "time" in command:
        now = time.strftime("%I:%M %p")
        speak(f"The current time is {now}")
        return

    if "date" in command:
        today = time.strftime("%B %d, %Y")
        speak(f"Today's date is {today}")
        return

    if "weather" in command:
        city = DEFAULT_CITY
        if " in " in command:
            city = command.split(" in ",1)[1].strip()
        else:
            speak("Which city do you want the weather for?")
            city_resp = listen_vosk()
            if city_resp:
                city = city_resp
        get_weather(city)
        return

    if "send email" in command or "email" in command:
        speak("Who is the recipient? Please type recipient email address:")
        to_addr = input("Recipient email: ").strip()
        speak("What is the subject?")
        subject = listen_vosk()
        speak("What should I say in the email?")
        message = listen_vosk()
        send_email(to_addr, subject, message)
        return

    if "remind me" in command or "set reminder" in command:
        speak("What should I remind you about?")
        text = listen_vosk()
        speak("In how many minutes should I remind you?")
        minutes_text = listen_vosk()
        try:
            minutes = int(''.join(ch for ch in minutes_text if ch.isdigit()))
            set_reminder(text, minutes)
        except:
            speak("I couldn't understand the time. Reminder not set.")
        return

    if command.startswith("who is") or command.startswith("what is") or command.startswith("tell me about"):
        q = command
        for prefix in ("who is", "what is", "tell me about"):
            if q.startswith(prefix):
                q = q.replace(prefix, "", 1).strip()
                break
        if q:
            answer_wikipedia(q)
        else:
            speak("What would you like to know about?")
            q2 = listen_vosk()
            if q2:
                answer_wikipedia(q2)
        return

    if "add command" in command or "create command" in command:
        speak("What phrase should trigger the command?")
        trigger = listen_vosk()
        if not trigger:
            speak("No trigger received. Cancelled.")
            return
        speak("What should I respond when you say that?")
        response = listen_vosk()
        if not response:
            speak("No response provided. Cancelled.")
            return
        custom_commands[trigger] = response
        save_custom_commands()
        speak(f"Custom command added for trigger: {trigger}")
        return

    if "help" in command or "commands" in command:
        speak("You can ask time, date, weather, set reminders, send email, ask Wikipedia, or add custom commands.")
        return

    speak("Sorry, I didn't understand that. You can say help to get a list of commands.")

# ----------------- MAIN LOOP -----------------
def main():
    speak("Advanced Voice Assistant with Vosk activated.")
    print("Speak a command or type one. Say 'exit' to stop.")
    while True:
        cmd = listen_vosk()
        if not cmd:
            cmd = input("Type command: ").strip().lower()
        try:
            process_command(cmd)
        except Exception as e:
            print("Processing error:", e)
            speak("An error occurred while processing your command.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        speak("Interrupted. Goodbye.")
        sys.exit(0)
