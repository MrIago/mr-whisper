# Inicia o mr-whisper no Windows (foreground).
# Para autostart no login: Task Scheduler → nova tarefa que roda este script no
# logon, ou um atalho na pasta Startup (shell:startup) apontando pra:
#   pythonw.exe <caminho>\app.py
$here = Split-Path -Parent $PSScriptRoot
python "$here\app.py"
