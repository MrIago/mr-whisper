# Inicia o mr-whisper no Windows (foreground).
# Para autostart no login: Task Scheduler → nova tarefa que roda este script no
# logon, ou um atalho na pasta Startup (shell:startup) apontando pra:
#   pythonw.exe <caminho>\daemon.py
$here = Split-Path -Parent $PSScriptRoot
python "$here\daemon.py"
