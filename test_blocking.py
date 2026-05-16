import sys, os
os.set_blocking(sys.stdout.fileno(), True)
os.set_blocking(sys.stderr.fileno(), True)
print("Blocking set to true")
