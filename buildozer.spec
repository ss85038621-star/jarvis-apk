[app]
title = JARVIS
package.name = jarvis
package.domain = org.jarvis
source.dir = .
source.include_exts = py
version = 1.0
requirements = python3,kivy==2.3.0,pyjnius,android,certifi,openssl
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,RECORD_AUDIO,MODIFY_AUDIO_SETTINGS,CAMERA,FLASHLIGHT,QUERY_ALL_PACKAGES,VIBRATE,com.android.alarm.permission.SET_ALARM
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
