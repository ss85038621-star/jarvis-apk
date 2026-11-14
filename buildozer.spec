[app]
title = JARVIS
package.name = jarvis
package.domain = org.jarvis
source.dir = .
source.include_exts = py
version = 1.0
requirements = python3,kivy==master,pyjnius,android,certifi,openssl
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

[buildozer]
log_level = 2
warn_on_root = 1
