import pandas as pd
import matplotlib.pyplot as plt

CSV_FILE = "telemetry_rocket_2000s.csv"

# ЗАГРУЗКА
df = pd.read_csv(CSV_FILE)
# ВРЕМЯ
ut = df["t"].values
t = ut - ut[0]# сек от начала

# ДАННЫЕ 
alt = df["altitude_km"].values
v = df["speed_ms"].values
m = df["mass"].values


# ALTITUDE 
plt.figure()
plt.plot(t, alt)
plt.xlabel("t, c")
plt.ylabel("Altitude, km")
plt.title("Altitude vs Time")
plt.grid(True)
plt.show()

# SPEED
plt.figure()
plt.plot(t, v)
plt.xlabel("t, c")
plt.ylabel("Speed, m/s")
plt.title("Speed vs Time")
plt.grid(True)
plt.show()

#  MASS
plt.figure()
plt.plot(t, m)
plt.xlabel("t, c")
plt.ylabel("Mass, kg")
plt.title("Mass vs Time")
plt.grid(True)
plt.show()



print("Графики построены")
