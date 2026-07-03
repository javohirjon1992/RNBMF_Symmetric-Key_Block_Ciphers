import subprocess

script_name = "Asosiynatijaolish.py"
processes = []

# 20 ta jarayonni ishga tushiramiz
for i in range(4):
    print(f"{i+1}-protsess ishga tushirildi...")
    p = subprocess.Popen(["python", script_name])
    processes.append(p)

# Barcha protsesslar tugashini kutamiz
for i, p in enumerate(processes, start=1):
    p.wait()
    print(f"{i}-protsess tugadi.")
