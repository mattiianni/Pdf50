' ─────────────────────────────────────────────────────────────
' Split PDF 50 — Launcher Windows
' Doppio click per avviare l'app (senza finestra CMD visibile)
' ─────────────────────────────────────────────────────────────

Dim WshShell, ScriptDir, BatPath

Set WshShell = CreateObject("WScript.Shell")
ScriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
BatPath = ScriptDir & "start.bat"

' Avvia il server (finestra minimizzata nel tray)
WshShell.Run Chr(34) & BatPath & Chr(34), 1, False

Set WshShell = Nothing
