import tkinter as tk
from tkinter import font
from tkinter import ttk
from PIL import ImageTk, Image
import sv_ttk
import serial, time, threading, json, subprocess, math
import matplotlib.pyplot as plt

# --------------- SERIAL VARIABLES
ARDUINO_PORT1 = "COM3"
ARDUINO_PORT2 = "COM5"
ARDUINO_PORT3 = "COM9"
ser_Arduino = None


# --------------- PICOSCOPE VARIABLES
picoEXE = r"C:\Users\wonga\Documents\PlatformIO\Projects\BA_Servo_Noise\Pico_Demo/pico_demo.exe"
delay_compensation = 0.15   # damit Pico und Servo position synchron sind ohne Blockierung
pico_plot_time = []
pico_plot_volt = []

# --------------- GUI VARIABLES
calc_win = None
AMLogo = Image.open('AMLogo.jpg')
scale = 0.8
w, h = AMLogo.size
smallLogo = AMLogo.resize((int(w*scale), int(h*scale)))


# --------------- GUI RING VARIABLES
ring_size = 300
ring_thickness = 4
ring_canvas = None
ring_box = None
noise_times = []


# --------------- PRESETS LADEN
preset_path = "preset_Teile.json"

def load_presets():
    try:
        with open (preset_path, "r", encoding="utf-8") as p:
            return json.load(p)
    except Exception as e:
        print("Fehler beim laden von Presets.", e)
presets = load_presets()

def set_entry(txtentry, decVal):
    if isinstance(decVal, (int, float)):
        val = f"{decVal}".replace('.' , ',')
    else:
        val = str(decVal)
    txtentry.delete(0, tk.END)
    txtentry.insert(0, val)
    
def insert_preset(p):
    set_entry(txtVolt, p["sollSpannung"])
    set_entry(txtAngle, p["sollWinkel"])


# --------------- SERIAL MIT SERVO
def open_first_available(ports=(ARDUINO_PORT1, ARDUINO_PORT2, ARDUINO_PORT3), baud=115200, timeout=2):
    last = None
    for p in ports:
        try:
            ser = serial.Serial(p, baudrate=baud, timeout=timeout)
            print(f"[SERIAL] Verbunden: {p}")
            time.sleep(1)
            return ser
        except Exception as e:
            last = e
    raise RuntimeError(f"Kein Port aus {ports} verfügbar: {last}")

def write_serial(gesamtW, gesamtS, stop_event, on_finish):
    try:
        pico_time = []
        pico_turn = []
        global pico_angle
        pico_angle = []
        global pico_plot_time
        pico_plot_time.clear()
        global pico_plot_volt
        pico_plot_volt.clear()

        ser_Arduino = open_first_available((ARDUINO_PORT1, ARDUINO_PORT2, ARDUINO_PORT3), baud=115200, timeout=5)
        time.sleep(0.2)
        ser_Arduino.write(f"SETW:{gesamtW}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"SETS:{gesamtS}\n".encode())
        time.sleep(0.2)
        print("speed ist", gesamtS)
        print("Sende: GO") #debug
        ser_Arduino.write(b"GO\n")

        ser_Arduino.timeout = 0.1
        while True:
            if stop_event.is_set():
                ser_Arduino.write(b"STOP\n")
                time.sleep(0.5)
                ser_Arduino.flush()
                time.sleep(0.2)
                break

            line = ser_Arduino.readline().decode('utf-8').strip()
            #print("Empfangen:", line) #debug
            if line.startswith("ANGLE"):
                global totalTicks
                totalTicks = float(line[5::])

            if line == 'READY':
                print("start run_pico")
                run_pico(ser_Arduino, pico_time, pico_plot_volt, pico_plot_time)

            elif line == 'FINISH':
                finish_time = time.time()
                totalDuration = finish_time - start_time
                print(f"FINISH empfangen, total Dauer: {totalDuration}")
                calc_rel_angle(pico_time, pico_turn, pico_angle)
                mark_ends()
                mark_noise_segments(pico_angle)
                set_circle_text()
                break

            elif line == 'CANCEL':
                break

            elif line.startswith("DELAY1"):
                global delaytime1
                delaytime1 = float(line[6::])
                print(f"{delaytime1}")
                
            elif line.startswith("DELAY2"):
                global delaytime2
                delaytime2 = float(line[6::])
                print(f"{delaytime2}")
                
            elif line.startswith("DELAY3"):
                global delaytime3
                delaytime3 = float(line[6::])
                print(f"{delaytime3}")
           
        ser_Arduino.close()

    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

    root.after(0, on_finish)


# --------------- DEBUG FUNCTION
"""
def go_left():
    try:
        global ser_Arduino
        if ser_Arduino is None or not ser_Arduino.is_open:
            print("Nicht verbunden.")
            return
        
        ser_Arduino.reset_input_buffer() 
        ser_Arduino.reset_output_buffer()
        time.sleep(1)
        print("LEFT geschrieben")
        ser_Arduino.write(b"LEFT\n")
        ser_Arduino.timeout = 0.1
        while True:
            line = ser_Arduino.readline().decode('utf-8').strip()
            print("Empfangen:", line) #debug
            if line == 'READY':
                break
            if line == 'CANCEL':
                break
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

def go_Right():
    try:
        ser_Arduino.write(b"RIGHT\n")
        print("RIGHT geschrieben")
        ser_Arduino.timeout = 0.1
        while True:
            line = ser_Arduino.readline().decode('utf-8').strip()
            print("Empfangen:", line) #debug
            if line == 'READY':
                break
            if line == 'CANCEL':
                break
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

def ser_Connect():
    try:
        global ser_Arduino
        if ser_Arduino is not None:
            ser_Arduino.close()
            ser_Arduino = None
            print("Serial Disconnected")
        else:
            ser_Arduino = open_first_available((ARDUINO_PORT1, ARDUINO_PORT2), baud=115200, timeout=5)
            ser_Arduino.reset_input_buffer() 
            ser_Arduino.reset_output_buffer()
            time.sleep(1)
            print("Serial Connected")
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

def curr_Pos():
    try:
        ser_Arduino.write(b"POS\n")
        print("POS geschrieben")
        ser_Arduino.timeout = 0.1
        while True:
            line = ser_Arduino.readline().decode('utf-8').strip()
            print("Empfangen:", line) #debug
            time.sleep(0.1)
            if line == 'READY':
                break
            if line == 'CANCEL':
                break
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

def goto():
    try:
        txtgoto = float(txtgo.get().strip())
        ser_Arduino.write(f"goto:{txtgoto}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(b"GOTO\n")
        print("GOTO geschrieben")
        ser_Arduino.timeout = 0.1
        while True:
            line = ser_Arduino.readline().decode('utf-8').strip()
            print("Empfangen:", line) #debug
            time.sleep(0.1)
            if line == 'READY':
                break
            if line == 'CANCEL':
                break
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug
"""

def go_zero(stop_event, on_finish):
    try:
        ser_Arduino = open_first_available((ARDUINO_PORT1,ARDUINO_PORT2, ARDUINO_PORT3), baud=115200, timeout=5)
        ser_Arduino.reset_input_buffer() 
        ser_Arduino.reset_output_buffer()
        time.sleep(1)
        print("zero geschrieben")
        ser_Arduino.write(b"ZERO\n")
        ser_Arduino.timeout = 0.1
        while True:
            if stop_event.is_set():
                ser_Arduino.write(b"STOP\n")
                ser_Arduino.flush()
                time.sleep(0.2)
                break
            line = ser_Arduino.readline().decode('utf-8').strip()
            print("Empfangen:", line) #debug
            if line == 'READY':
                break
            if line == 'CANCEL':
                break
        ser_Arduino.close()
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

    root.after(0, on_finish)


# --------------- CALC FUNCTIONS
def calc_duration(gesSpeed):
    totalDelay = delaytime1 + delaytime2 + delaytime3
    userRPM = float(gesSpeed)
    duration = 0
    circleTick = 4096
    for i in range(1, 4, 1):
        divSpeed = userRPM/2
        duration += 2 * (60/(divSpeed*i)) * (totalTicks/circleTick)
    duration = duration + totalDelay # wegen servo delay für jeden antrieb
    return duration

def calc_individual_turns(gesSpeed, turnNumber):
    userRPM = float(gesSpeed)
    total_duration = 0
    circleTick = 4096
    for i in range(1, 4, 1):
        divSpeed = userRPM/2
        turn_duration = (60/(divSpeed*i)) * (totalTicks/circleTick)
        total_duration += 2 * turn_duration
        match i:
            case 1:
                time1 = total_duration + delaytime1
                turn1 = turn_duration + (delaytime1 / 2)
            case 2:
                time2 = total_duration + delaytime1 + delaytime2
                turn2 = turn_duration + (delaytime2 / 2)
            case 3:
                time3 = total_duration + delaytime1 + delaytime2 + delaytime3
                turn3 = turn_duration + (delaytime3 / 2)

    match turnNumber:
        case 1: return time1
        case 2: return time2
        case 3: return time3
        case 4: return turn1
        case 5: return turn2
        case 6: return turn3

def calc_rel_angle(time_arr, turn_arr, angle_arr):
    userRPM = float(txtSpeed.get().strip().replace(',', '.'))
    time1 = calc_individual_turns(userRPM, 1)
    time2 = calc_individual_turns(userRPM, 2)
    time3 = calc_individual_turns(userRPM, 3)

    turn1 = calc_individual_turns(userRPM, 4)
    turn2 = calc_individual_turns(userRPM, 5)
    turn3 = calc_individual_turns(userRPM, 6)
    
    if not time_arr:
        return 
    
    # Wenn Zeit evtl. schöner machen?
    for i in range(len(time_arr)):
        if time_arr[i] < turn1:
            turn_arr.append(1)
            angle_arr.append((time_arr[i])/(turn1)*360)
        elif time_arr[i] < time1:
            turn_arr.append(2)
            angle_arr.append(360-((time_arr[i]-turn1)/(turn1)*360))
        elif time_arr[i] < time2-turn2:
            turn_arr.append(3)
            angle_arr.append((time_arr[i]-time1)/(turn2)*360)
        elif time_arr[i] < time2:
            turn_arr.append(4)
            angle_arr.append(360-((time_arr[i]-time1-turn2)/(turn2)*360))
        elif time_arr[i] < time3-turn3:
            turn_arr.append(5)
            angle_arr.append((time_arr[i]-time2)/(turn3)*360)
        elif time_arr[i] < time3:
            turn_arr.append(6)
            angle_arr.append(360-((time_arr[i]-time2-turn3)/(turn3)*360))


    print(turn1)
    print(time1)
    print(time2-turn2)
    print(time2)
    print(time3-turn3)
    print(time3)
    print(turn_arr)
    print(angle_arr)
    return 

def calc_delay():
    return

def run_pico(ser_Ard, time_arr, volt_arr, plot_arr):
    global start_time
    out_found = False
    plot_volt = False
    plot_time = False
    txtGeschw = float(txtSpeed.get().strip().replace(',', '.'))
    picoTime = calc_duration(txtGeschw)
    print(f"Dauer ca. {picoTime}")
    print(f"Winkellänge {totalTicks*(360/4096)}")
    picoTimeStr = str(picoTime+delay_compensation)
    p = subprocess.Popen(
        [picoEXE, f"--time={picoTimeStr}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    for line in p.stdout:
        line = line.strip()
        print(line)

        if line.startswith("PICO_START"):
            print("Sende: PICO_START") #debug
            ser_Ard.write(b"START\n")
            ser_Ard.flush()
            
            start_time = time.time()
            print("NACH: PICO_START")
        
        if out_found is True:
            time_arr.append(float(line)-delay_compensation)

        if line.startswith("OUTPUT"):
            out_found = True
            plot_volt = False

        if plot_volt is True:
            volt_arr.append(float(line))

        if line.startswith("PLOT_VOLT"):
            plot_volt = True 
            plot_time = False

        if plot_time is True:
            plot_arr.append(float(line))

        if line.startswith("PLOT_TIME"):
            plot_time = True

    end_time = time.time()
    print("Time Array:")
    print(time_arr)
    #print("Volt Array:")
    #print(volt_arr)
    #print("Plot Array:")
    #print(plot_arr)
    finishtime = end_time - start_time
    print(f"Gemessene Zeit: {finishtime}")
    p.terminate()


# --------------- GUI FUNCTIONS
def close_window():
    root.destroy()

def open_calc_win():
    def close_wait_results():
        wait_win.destroy()

        if stop_event.is_set():
            global cancelled_win
            
            cancelled_win = tk.Toplevel(root)
            cancelled_win.title("Abbruch")
            cancelled_win.geometry(f"{scrwid//4}x{scrhei//4}+{scrwid//2}+{scrhei//2}")
            cancelled_win.grid_rowconfigure(0, weight=1)
            cancelled_win.grid_rowconfigure(1, weight=1)
            cancelled_win.grid_columnconfigure(0, weight=1)
            
            ttk.Label(cancelled_win, text="Vorgang wurde abgebrochen.").grid(row=0, column=0)
            ok_button = ttk.Button(cancelled_win, text="OK", command=cancelled_win.destroy)
            ok_button.grid(row=1, column=0, pady=(0, 20), ipadx=20)
            ok_button.focus_set()  
            cancelled_win.bind("<Return>", lambda event: ok_button.invoke())
        else:
            global calc_win
            if calc_win is not None and calc_win.winfo_exists():
                calc_win.destroy()
            """
            calc_win = tk.Toplevel(root)
            calc_win.title("Fertig")
            calc_win.geometry(f"{scrwid//4}x{scrhei//4}+{scrwid//2}+{scrhei//2}")
            calc_win.grid_rowconfigure(0, weight=1)
            calc_win.grid_rowconfigure(1, weight=1)
            calc_win.grid_columnconfigure(0, weight=1)
            
            ttk.Label(calc_win, text="Messung erfolgreich!").grid(row=0, column=0)
            ok_button = ttk.Button(calc_win, text="OK", command=calc_win.destroy)
            ok_button.grid(row=1, column=0, pady=(0, 20), ipadx=20)
            ok_button.focus_set()  
            calc_win.bind("<Return>", lambda event: ok_button.invoke())
            """
    try:
        txtSoll = float(txtVolt.get().strip().replace(',', '.'))
        txtWinkel = float(txtAngle.get().strip().replace(',', '.'))
        txtGeschw = float(txtSpeed.get().strip().replace(',', '.'))

    except ValueError:
        error_win = tk.Toplevel(root)
        error_win.title("Falsche Eingabe!")
        error_win.geometry(f"{scrwid//8}x{scrhei//8}+{scrwid//2}+{scrhei//2}")
        error_win.resizable(False, False)
        error_win.transient(root)
        error_win.grab_set()
        error_win.grid_rowconfigure(0, weight=1)
        error_win.grid_rowconfigure(1, weight=1)
        error_win.grid_columnconfigure(0, weight=1)
        error_win.bell()
        ttk.Label(error_win, text="Leeres Feld gefunden!").grid(row=0, column=0)
        ok_button = ttk.Button(error_win, text="OK", command=error_win.destroy)
        ok_button.grid(row=1, column=0, ipadx=20)
        ok_button.focus_set()
        error_win.bind("<Return>", lambda event: ok_button.invoke())
        return
        
    wait_win = tk.Toplevel(root)
    wait_win.title("Datenmessung")
    wait_win.geometry(f"{scrwid//8}x{scrhei//8}+{scrwid//2}+{scrhei//2}")
    wait_win.transient(root)
    wait_win.grab_set()
    wait_win.resizable(False, False)
    ttk.Label(wait_win, text="Bitte warten...").pack(pady=30)

    
    stop_event = threading.Event()    
    def cancel_close():
        stop_event.set()
        wait_win.destroy()
    wait_win.protocol("WM_DELETE_WINDOW", cancel_close)


    threading.Thread(target=write_serial, args=(txtWinkel, txtGeschw, 
                                                   stop_event, close_wait_results), daemon=True).start()

    
# --------------- OPEN ZERO WINDOW
def open_zero_window():
    def close_wait_results():
        wait_win.destroy()

        if stop_event.is_set():
            global cancelled_win
            
            cancelled_win = tk.Toplevel(root)
            cancelled_win.title("Abbruch")
            cancelled_win.geometry(f"{scrwid//4}x{scrhei//4}+{scrwid//2}+{scrhei//2}")
            cancelled_win.grid_rowconfigure(0, weight=1)
            cancelled_win.grid_rowconfigure(1, weight=1)
            cancelled_win.grid_columnconfigure(0, weight=1)
            
            ttk.Label(cancelled_win, text="Vorgang wurde abgebrochen.").grid(row=0, column=0)
            ok_button = ttk.Button(cancelled_win, text="OK", command=cancelled_win.destroy)
            ok_button.grid(row=1, column=0, pady=(0, 20), ipadx=20)
            ok_button.focus_set()  
            cancelled_win.bind("<Return>", lambda event: ok_button.invoke())
        else:
            global calc_win
            if calc_win is not None and calc_win.winfo_exists():
                calc_win.destroy()

            calc_win = tk.Toplevel(root)
            calc_win.title("Fertig")
            calc_win.geometry(f"{scrwid//4}x{scrhei//4}+{scrwid//2}+{scrhei//2}")
            calc_win.grid_rowconfigure(0, weight=1)
            calc_win.grid_rowconfigure(1, weight=1)
            calc_win.grid_columnconfigure(0, weight=1)
            
            ttk.Label(calc_win, text="Position ist auf 0.").grid(row=0, column=0)
            ok_button = ttk.Button(calc_win, text="OK", command=calc_win.destroy)
            ok_button.grid(row=1, column=0, pady=(0, 20), ipadx=20)
            ok_button.focus_set()  
            calc_win.bind("<Return>", lambda event: ok_button.invoke())
        
    wait_win = tk.Toplevel(root)
    wait_win.title("Position nullen")
    wait_win.geometry(f"{scrwid//8}x{scrhei//8}+{scrwid//2}+{scrhei//2}")
    wait_win.transient(root)
    wait_win.grab_set()
    wait_win.resizable(False, False)
    ttk.Label(wait_win, text="Bitte warten...").pack(pady=30)

    stop_event = threading.Event()    
    def cancel_close():
        stop_event.set()
        wait_win.destroy()
    wait_win.protocol("WM_DELETE_WINDOW", cancel_close)
    threading.Thread(target=go_zero, args=(stop_event, close_wait_results), daemon=True).start()


# --------------- PDF EXPORT RAUSCHKURVE
def save_to_pdf():
    fig = plt.figure(figsize=(11, 6.5), dpi=550)  # Größe beliebig anpassen
    plt.plot(pico_plot_time, pico_plot_volt, linewidth=0.1)
    plt.title(("Rauschkurve "+ txt9.get()))
    plt.xlabel("Zeit")
    plt.ylabel("Spannung")
    plt.grid(True, linestyle="--", linewidth=0.6, alpha=0.6)
    plt.tight_layout()
    fig.savefig((txt9.get()+".pdf"), format="pdf")  # Vektor-PDF
    plt.close(fig)
"""
if __name__ == "__main__":
    x = [1, 2, 1, 3, 4, 3]
    y = [1, 2, 3, 4, 5, 6]
    save_xy_to_pdf(x, y, filename="xy_plot.pdf", title="x–y Plot")
    print("PDF geschrieben: xy_plot.pdf")
"""


# --------------- GUI
root = tk.Tk()
scrwid = root.winfo_screenwidth()
scrhei = root.winfo_screenheight()
root.geometry(f"{scrwid - scrwid//5}x{scrhei - scrhei//5}+0+0")
root.title("Rauschprüfung")
root.resizable(False, False)


root.grid_columnconfigure(0, weight=0)
root.grid_columnconfigure(1, weight=1)
root.grid_rowconfigure(0, weight=0)
root.grid_rowconfigure(1, weight=1)

left_frame  = ttk.Frame(root)
right_frame = ttk.Frame(root)
left_frame.grid(row=1, column=0, sticky="nw", padx=12, pady=12)
right_frame.grid(row=1, column=1, sticky="nw",  padx=12, pady=12)
ring_area = ttk.Frame(root)
ring_area.grid(row=1, column=2, sticky="nw",  padx=120, pady=12)

img = ImageTk.PhotoImage(smallLogo)
panel = tk.Label(root, image=img)
panel.image = img    
panel.grid(row=0, column=0, columnspan=2,padx=24, pady=24, sticky="nw")

ttk.Label(left_frame, text="Bauteil Preset:").grid(row=0, column=0, sticky="w", pady=(10, 0), padx=(20,0))
preset_names = list(presets.keys()) 
preset_combo = ttk.Combobox(left_frame, values=preset_names, state="readonly", width=16)
preset_combo.grid(row=1, column=0, sticky="w", padx=(20,0))
preset_combo.current(0)

def on_select_preset(event=None):
    name = preset_combo.get()
    if name in presets:
        insert_preset(presets[name])

preset_combo.bind("<<ComboboxSelected>>", on_select_preset)


right_frame.grid_columnconfigure(1, weight=0)
# right_frame.grid_rowconfigure(0, weight=0)

vcmd = (root.register(lambda P: (P.count(',') <= 1 and all(ch.isdigit() or ch == ',' for ch in P))), "%P")

ttk.Label(left_frame, text="Auftragsnummer:").grid(row=4, column=0, sticky="w", pady=(20, 0), padx=(20,0))
txt9 = ttk.Entry(left_frame, width=20)
txt9.grid(row=5, column=0, pady=(0, 10), padx=(20,0))

ttk.Label(right_frame, text="Sollspannung in V:").grid(row=1, column=0, sticky="w", pady=(40, 0), padx=(10,0))
txtVolt = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txtVolt.grid(row=2, column=0, pady=(0, 0), padx=(0,0))
txtVolt.insert(0, "5,0")
txtVolt.focus_set()
ttk.Label(right_frame, text="Gesamtwinkel in Grad:").grid(row=3, column=0, sticky="w", pady=(40, 0), padx=(10,0))
txtAngle = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txtAngle.grid(row=4, column=0, pady=(0, 0), padx=(0,0))
txtAngle.insert(0, "330,0")
ttk.Label(right_frame, text="Max. Geschwindigkeit in U/min:").grid(row=5, column=0, sticky="w", pady=(40, 0), padx=(10,0))
txtSpeed = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txtSpeed.grid(row=6, column=0, pady=(0, 0), padx=(0,0))
txtSpeed.insert(0, "60,0")



# txtgo = ttk.Entry(left_frame, width=20, validate="key", validatecommand=vcmd)
# txtgo.grid(row=3, column=1, pady=(0, 0), padx=(0,0))

ttk.Button(left_frame, text="Abbrechen", command=close_window).grid(row=7, column=0, pady=(4, 5), padx=(0,0), ipadx=40)
ttk.Button(left_frame, text="Messen", command=open_calc_win).grid(row=6, column=0, pady=(80, 5), padx=(0,0), ipadx=40)
ttk.Button(right_frame, text="Rauschkurve speichern", command=save_to_pdf).grid(row=7, column=0, pady=(107, 5), padx=(0,0), ipadx=10)
ttk.Button(left_frame, text="Position 0", command=open_zero_window).grid(row=8, column=0, pady=(80, 5), padx=(0,0), ipadx=40)
# ttk.Button(left_frame, text="0.1 Links", command=go_left).grid(row=6, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
# ttk.Button(left_frame, text="0.1 Rechts", command=go_Right).grid(row=7, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
# ttk.Button(left_frame, text="Conn Serial", command=ser_Connect).grid(row=5, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
# ttk.Button(left_frame, text="Curr Position", command=curr_Pos).grid(row=8, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
# ttk.Button(left_frame, text="Go To", command=goto).grid(row=4, column=1, pady=(4, 5), padx=(0,0), ipadx=40)

txtVolt.bind("<Return>", lambda event: open_calc_win())
txtAngle.bind("<Return>", lambda event: open_calc_win())
root.bind("<Escape>", lambda event: close_window())


# --------------- GUI RING FÜR FEHLER
def build_ring(frame):
    global ring_canvas, ring_box
    ring_canvas = tk.Canvas(
        frame, width=ring_size+30, height=ring_size+30,
        bg=root.cget("background")
    )
    ring_canvas.pack()
    canv_x = canv_y = ring_size // 2 + 15
    radius = (ring_size // 2) - 18
    ring_box = (canv_x - radius, canv_y - radius, canv_x + radius, canv_y + radius)
    ring_canvas.create_arc(ring_box, start=0, extent=359.9,
                           style="arc", width=ring_thickness, outline="#6b6b6b")
    
    for deg in range(0, 360, 10):
        long_tick = (deg % 30 == 0)
        L = 30 if long_tick else 12
        rad = math.radians(deg - 90)
        x0 = canv_x + (radius + ring_thickness/2) * math.cos(rad)
        y0 = canv_y + (radius + ring_thickness/2) * math.sin(rad)
        x1 = canv_x + (radius + L) * math.cos(rad)
        y1 = canv_y + (radius + L) * math.sin(rad)
        ring_canvas.create_line(x0, y0, x1, y1, width=4, fill="#ffffff")

def mark_ends():
    fix_direction = -90
    line_span = (totalTicks/4096)*360
    line_side = line_span/2
    L = 50

    clear_noise_marks()
    
    for deg in range(-1,2,2):
        canv_x = canv_y = ring_size // 2 + 15
        radius = (ring_size // 2) - 18
        rad = math.radians(deg*line_side + fix_direction)
        x0 = canv_x + (radius + ring_thickness/2- L/2) * math.cos(rad)
        y0 = canv_y + (radius + ring_thickness/2- L/2) * math.sin(rad)
        x1 = canv_x + (radius + L+ L/2) * math.cos(rad)
        y1 = canv_y + (radius + L+ L/2) * math.sin(rad)
        iid = ring_canvas.create_line(x0, y0, x1, y1, width=8, fill="#00ffff")
        noise_times.append(iid)

def clear_noise_marks():
    global noise_times
    for iid in noise_times:
        ring_canvas.delete(iid)
    noise_times = []

def mark_noise_segments(angle_arr, color="#ff0000"):
    global noise_times
    fix_direction = -90

    for i in range(len(angle_arr)):
        tol_left = angle_arr[i]+fix_direction+2.5
        tol_right = -5
        iid = ring_canvas.create_arc(ring_box, start=tol_left, extent=tol_right,
                                     style="arc", width=ring_thickness+10, outline="#ff0000")
        noise_times.append(iid)

def set_circle_text():
    x0, y0, x1, y1 = ring_box
    canv_x = (x0 + x1) / 2
    canv_y = (y0 + y1) / 2
    text_font = font.Font(family="Arial", size=20, weight="bold")

    if not pico_angle:
        iid = ring_canvas.create_text(
                canv_x, canv_y, text="In Ordnung", fill="#00ff33",
                font=text_font, anchor="center")
    else:
        iid = ring_canvas.create_text(
                canv_x, canv_y, text="Fehler", fill="#ff0000",
                font=text_font, anchor="center")
    noise_times.append(iid)


# --------------- MAIN
build_ring(ring_area)
on_select_preset()
sv_ttk.set_theme("dark")
root.mainloop()