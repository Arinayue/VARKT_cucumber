import krpc
import _thread as thread
import time
import math
import pandas as pd

# Подключаемся к KSP через kRPC
connection = krpc.connect(name='fygep', address='127.0.0.1', rpc_port=50002, stream_port=50003)

# Получаем доступ к объектам управления кораблем
space_center = connection.space_center  # объект космического центра
vessel = space_center.active_vessel  # активный космический корабль

# Создаем поток для текущего игрового времени (universal time)
ut_stream = connection.add_stream(getattr, space_center, 'ut')

# Получаем информацию о полете
flight = vessel.flight()

# Создаем потоки телеметрии для скорости, высоты и массы
altitude_stream = connection.add_stream(getattr, flight, 'mean_altitude')  # высота
mass_stream = connection.add_stream(getattr, vessel, 'mass')  # масса
speed = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')  # скорость

# Словарь для хранения телеметрии
telemetry = {
    "t": [],  # время
    "altitude_km": [],  # высота в км
    "speed_ms": [],  # скорость в м/с
    "mass": []  # масса корабля
}

# Переменные для записи
t0 = None  # начальное время
MAX_TIME = 2000.0  # максимальное время записи
DT = 1.0  # интервал записи телеметрии
last_ut = 0.0
logging_active = True  # флаг активного записи

# Функция записи телеметрии
def data_logger():
    global t0, last_ut, logging_active

    while logging_active:
        ut = ut_stream()  # текущее игровое время
        if t0 is None:  # задаем начальное время
            t0 = ut
            last_ut = ut

        t = ut - t0  # время с начала миссии

        if t > MAX_TIME:  # останавливаем запись по достижении лимита 2000
            logging_active = False
            break
        
        if ut - last_ut >= DT:  # записываем данные через интервалы DT
            telemetry["t"].append(t)
            telemetry["altitude_km"].append(altitude_stream() / 1000.0)  # переводим в км
            telemetry["speed_ms"].append(speed())
            telemetry["mass"].append(mass_stream())

            last_ut = ut

        time.sleep(0.05)

    print("Zapis zaversh")  # сообщение об окончании записи


# Аргументы для мониторинга
args = [vessel]

# Функция мониторинга топлива и стадий
def monitor(vessel):
    time.sleep(3)
    while True:
        # Получаем ресурсы текущей активной ступени
        resources = vessel.resources_in_decouple_stage(vessel.control.current_stage - 1, False)

        solidFuel = resources.amount("SolidFuel")
        liquidFuel = resources.amount("LiquidFuel")

        # Если топливо закончилось, активируем следующую стадию
        if solidFuel <= 0 and liquidFuel <= 0:
            vessel.control.activate_next_stage() 
            print("Rasdelinie")  # сообщение о отделении ступени

        time.sleep(0.2)


# Функция подъема на орбиту Кербина
def engage_1(vessel, space_center, connection, ascentProfileConstant=1.25):
    vessel.control.rcs = True  # включаем RCS
    vessel.control.throttle = 1  # полный газ

    # Поток для апоапсиса орбиты
    apoapsisStream = connection.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')

    vessel.auto_pilot.engage()  # включаем автопилот
    vessel.auto_pilot.target_heading = 90 # курс на 90 градусов

    # Подъем до апоапсиса 75 км
    while apoapsisStream() < 75000:
        targetPitch = 90 - ((90/(75000**ascentProfileConstant))*(apoapsisStream()**ascentProfileConstant))
        vessel.auto_pilot.target_pitch = targetPitch  # регулировка наклона

        time.sleep(0.1)

    vessel.control.throttle = 0  # выключаем двигатель
    # Потоки времени до апоапсиса и перигея
    timeToApoapsisStream = connection.add_stream(getattr, vessel.orbit, 'time_to_apoapsis')
    periapsisStream = connection.add_stream(getattr, vessel.orbit, 'periapsis_altitude')

    # Ждем стабилизации орбиты
    while(timeToApoapsisStream() > 22):
        if(timeToApoapsisStream() > 60):
            space_center.rails_warp_factor = 4  # ускорение времени
        else:
            space_center.rails_warp_factor = 0

        time.sleep(0.5)

    # Тонкая настройка перигея для стабильной орбиты
    vessel.control.throttle = 0.5
    lastUT = space_center.ut
    lastTimeToAp = timeToApoapsisStream()
    while(periapsisStream() < 70500):
        time.sleep(0.2)
        timeToAp = timeToApoapsisStream()
        # Вычисляем скорость изменения времени до апоапсиса
        deltaTimeToAp = (timeToAp - lastTimeToAp) / (space_center.ut - lastUT)
        
        # Пропорциональная регулировка газа
        if deltaTimeToAp < -0.3:
            vessel.control.throttle += 0.03
        elif deltaTimeToAp < -0.1:
            vessel.control.throttle += 0.01

        if deltaTimeToAp > 0.2:
            vessel.control.throttle -= 0.03
        elif deltaTimeToAp > 0:
            vessel.control.throttle -= 0.01

        lastTimeToAp = timeToApoapsisStream()
        lastUT = space_center.ut

    vessel.control.throttle = 0
    print("Orbita")  # корабль на орбите Кербина


# Подготовка к перелету на Луну
def engage_2(vessel, space_center):
    vessel.control.rcs = True
    fairings = vessel.parts.fairings # Получаем список обтекателей корабля
    for fairing in fairings:
        fairing.jettison()  # сброс обтекателей
    vessel.control.antennas = True  # включаем антенны

    # Вычисление оптимального фазового угла для встречи с Луной
    destSemiMajor = space_center.bodies["Mun"].orbit.semi_major_axis # Большая полуось орбиты Луны вокруг Кербина
    hohmannSemiMajor = destSemiMajor / 2 # Половина большой полуоси, используется для расчета маневра Хоумана
    neededPhase = 2 * math.pi * (1 / (2 * (destSemiMajor ** 3 / hohmannSemiMajor ** 3) ** (1 / 2))) # Вычисляем фазовый угол, при котором нужно запускать трансфер на Луну
    optimalPhaseAngle = 180 - neededPhase * 180 / math.pi  # Перевод в градусы — оптимальный угол для запуска

    phaseAngle = 1080 # Начальное значение фазового угла
    vessel.auto_pilot.engage()
    vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
    vessel.auto_pilot.target_direction = (0.0, 1.0, 0.0)

    # Ждем нужного фазового угла
    angleDec = False
    prevPhase = 0
    while abs(phaseAngle - optimalPhaseAngle) > 1 or not angleDec:
        # Радиусы орбит Луны и корабля
        bodyRadius = space_center.bodies["Mun"].orbit.radius
        vesselRadius = vessel.orbit.radius

        time.sleep(1)
        # Получаем текущие позиции Луны и корабля в выбранной рамке отсчета
        bodyPos = space_center.bodies["Mun"].orbit.position_at(space_center.ut, space_center.bodies["Mun"].reference_frame)
        vesselPos = vessel.orbit.position_at(space_center.ut, space_center.bodies["Mun"].reference_frame)
        # Вычисляем расстояние между кораблем и Луной
        bodyVesselDistance = ((bodyPos[0] - vesselPos[0])**2 + (bodyPos[1] - vesselPos[1])**2 + (bodyPos[2] - vesselPos[2])**2)**(1/2)
        # Вычисляем фазовый угол с использованием теоремы косинусов
        try:
            phaseAngle = math.acos((bodyRadius**2 + vesselRadius**2 - bodyVesselDistance**2) / (2 * bodyRadius * vesselRadius))
        except:
            continue
        phaseAngle = phaseAngle * 180 / math.pi

        if prevPhase - phaseAngle > 0:
            angleDec = True
            if abs(phaseAngle - optimalPhaseAngle) > 20:
                space_center.rails_warp_factor = 2 # Среднее ускорение времени
            else:
                space_center.rails_warp_factor = 0 # Реальное время
        else:
            angleDec = False
            space_center.rails_warp_factor = 4 # Быстрое ускорение времени

        prevPhase = phaseAngle

    # Расчет дельта-V для маневра на Луну
    GM = vessel.orbit.body.gravitational_parameter # Гравитационный параметр Кербина
    r = vessel.orbit.radius # Текущий радиус орбиты
    a = vessel.orbit.semi_major_axis # Полуось орбиты
    # Скорость после маневра Хоумана
    initialV = (GM * ((2/r) - (1/a)))**(1/2) # Начальная орбитальная скорость
    a = (space_center.bodies["Mun"].orbit.radius + vessel.orbit.radius) / 2
    finalV = (GM * ((2/r) - (1/a)))**(1/2)
    deltaV = finalV - initialV # Дельта-V — сколько нужно прибавить скорости для перехода на Луну

    # Разгон до нужной скорости
    actualDeltaV = 0
    vessel.control.throttle = 1.0
    while(deltaV > actualDeltaV):
        time.sleep(0.15)
        r = vessel.orbit.radius
        a = vessel.orbit.semi_major_axis
        actualDeltaV = (GM * ((2/r) - (1/a)))**(1/2) - initialV
    vessel.control.throttle = 0
    vessel.auto_pilot.disengage()

    print("luna")  # корабль готов к перелету на Луну


# Выход на орбиту Луны
def engage_3(vessel, space_center):
    vessel.control.rcs = True
    vessel.control.antennas = True
    vessel.auto_pilot.engage()
    vessel.auto_pilot.reference_frame = vessel.surface_velocity_reference_frame
    vessel.auto_pilot.target_direction = (0.0, -1.0, 0.0)

    vessel.auto_pilot.wait()
    # Ускоряем время до момента перигея Луны
    time_to_warp = vessel.orbit.time_to_periapsis
    space_center.warp_to(space_center.ut + time_to_warp - 30)

    vessel.auto_pilot.wait()

    vessel.control.throttle = 1
    time.sleep(12)  # небольшой импульс для выхода на орбиту
    vessel.control.throttle = 0
    print("Orbita luna")  # корабль на орбите Луны


# Запуск потоков для записи телеметрии и мониторинга топлива
thread.start_new_thread(data_logger, ())
thread.start_new_thread(monitor, tuple(args))

# Подъем на орбиту Кербина
engage_1(vessel, space_center, connection, 0.5)

# Маневр на Луну
engage_2(vessel, space_center)
time_to_warp = vessel.orbit.next_orbit.time_to_periapsis + vessel.orbit.time_to_soi_change
space_center.warp_to(space_center.ut + time_to_warp - 300)  # ускорение до вхождения в сферу влияния Луны

# Выход на орбиту Луны
engage_3(vessel, space_center)

print("Vse")  # миссия завершена

# Сохраняем телеметрию в CSV
#df = pd.DataFrame(telemetry)
#df.to_csv("telemetry_rocket_2000s.csv", index=False)
#print("telemetry_rocket_2000s.csv")  # сообщение о сохранении
