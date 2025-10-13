import tkinter as tk
from tkinter import ttk
from PIL import ImageTk, Image
import sv_ttk
import serial, time, threading, json, os, re
from itertools import cycle
from datetime import datetime
import pandas as pd
import xlsxwriter
from openpyxl import load_workbook

ARDUINO_PORT1 = "COM3"
ARDUINO_PORT2 = "COM6"
MULTI_PORT = "COM7"


calc_win = None
ser_Arduino = None
AMLogo = Image.open('AMLogo.jpg')
scale = 0.8
w, h = AMLogo.size
smallLogo = AMLogo.resize((int(w*scale), int(h*scale)))


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
    set_entry(txt1, p["sollSpannung"])
    set_entry(txt6, p["sollWinkel"])
    set_entry(txt2, p["d11"])
    set_entry(txt3, p["d12"])
    set_entry(txt4, p["d21"])
    set_entry(txt5, p["d22"])
    set_entry(txt7, p["d31"])
    set_entry(txt8, p["d32"])

# --------------- SERIAL MIT MULTIMETER

def RegexMultimeter(output):
    match = re.search(r"[-+]?\d\.\d+(?:[Ee][-+]\d+)", output)
    #match = re.search("[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?", output)
    if match:
        return match.group(0)
    return None

# --------------- SERIAL MIT SERVO

labels = [  "Mittelposition",
            "Start aktiver Bereich CW (Drehrichtung-)",
            "50° CW (25% aktiver Bereich)(Drehrichtung-)",
            "75° CW (50% aktiver Bereich)(Drehrichtung-)",
            "100° CW (75% aktiver Bereich)(Drehrichtung-)",
            "Ende aktiver Bereich CW (Drehrichtung-)(11) 10V",
            "Mechanisches Ende CW (Drehrichtung-)",
            "Start aktiver Bereich CCW (Drehrichtung+)",
            "50° CCW (25% aktiver Bereich)(Drehrichtung+)",
            "75° CCW (50% aktiver Bereich)(Drehrichtung+)",
            "100° CCW (75% aktiver Bereich)(Drehrichtung+)",
            "Ende aktiver Bereich CCW (Drehrichtung+)(13) 0V",
            "Mechanisches Ende CCW (Drehrichtung+)"]
labels_iter = cycle(labels)

def open_first_available(ports=(ARDUINO_PORT1, ARDUINO_PORT2), baud=115200, timeout=2):
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

def write_serial(gesamtV, gesamtW, d11, d12, d21, d22, d31, d32, stop_event, on_finish):
    try:
        ser_Arduino = open_first_available(("COM6","COM3"), baud=115200, timeout=5)
        try:
            ser_Multi = serial.Serial(MULTI_PORT, baudrate=9600, timeout = 0.5)
            print(f"[SERIAL] Verbunden: {MULTI_PORT}")
        except Exception as e:
            print("Multimeter kein Port")
        N = 13 #Anz Messpunkte wegen leere Zellen
        daten = []
        linear_sollV = [None] * N
        linear_lin = [None] * N
        error_lin_idx = set()
        lin_max = None
        lin_min = None
        summary_vals = {}
        time.sleep(0.2)
        ser_Arduino.write(f"SETV:{gesamtV}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"SETW:{gesamtW}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"dead11:{d11}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"dead12:{d12}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"dead21:{d21}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"dead22:{d22}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"dead31:{d31}\n".encode())
        time.sleep(0.2)
        ser_Arduino.write(f"dead32:{d32}\n".encode())
        time.sleep(0.2)
        print("Sende: GO") #debug
        #print(d11, d12, d21, d22, d31, d32)
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
            print("Empfangen:", line) #debug
            if line == 'VOLTR':
                ser_Multi.reset_input_buffer()
                ser_Multi.reset_output_buffer()
                ser_Multi.write(b':MEAS:VOLT:DC?\n')
                #print("geschrieben")
                time.sleep(0.05)
                #print("sleep 0.2 sek")
                response = ser_Multi.readline().decode('utf-8', errors='ignore').strip()
                #print("geantwortet")
                if(RegexMultimeter(response)):
                    #print("check1")
                    voltage  = float(RegexMultimeter(response))
                    #print("check2")
                    print(voltage)
                    ser_Arduino.write(f"ISTV:{voltage}\n".encode())
                    #print("check3")
                else:
                    print("Problem bei Response")
                    None
                continue
            elif line.startswith("SUMMARY;"):
                try:
                    parts = line.split(";")[1:]
                    for p in parts:
                        if ":" in p:
                            i, val = p.split(":", 1)
                            summary_vals[i] = float(val)
                except Exception as e:
                    print("Fehler SUMMARY-Parse:", e)
                continue
            elif line.startswith("LINEAR;"):
                try:
                    parts = dict(p.split(":", 1) for p in line.split(";")[1:])
                    i = int(parts["idx"])
                    if "Soll-Spannung Real" in parts:
                        linear_sollV[i] = float(parts["Soll-Spannung Real"])
                        print(linear_sollV[i])
                    if "Linearität" in parts:
                        linear_lin[i] = float(parts["Linearität"])
                        print(linear_lin[i])
                except Exception as e:
                    print("Fehler LINEAR-Parse:", e)
                continue
            elif line.startswith("ERROR_LIN;"):
                try:
                    parts = dict(p.split(":", 1) for p in line.split(";")[1:])
                    
                    idx_str = parts.get("IDX", "")
                    if idx_str:
                        error_lin_idx = {int(s) for s in idx_str.split(",") if s.strip().isdigit()}
                    
                    if "LIN_MAX" in parts:
                        lin_max = float(parts["LIN_MAX"])
                    if "LIN_MIN" in parts:
                        lin_min = float(parts["LIN_MIN"])
                except Exception as e:
                    print("Fehler ERROR_LIN-Parse:", e)
                continue
            elif line.startswith("Soll-Winkel:"):
                try:
                    parts = line.split(";")
                    sollwinkel = float(parts[0].split(":")[1])
                    sollspannung = float(parts[1].split(":")[1])
                    istspannung = float(parts[2].split(":")[1])
                    istwinkel = float(parts[3].split(":")[1])
                    realwinkelmitte = float(parts[4].split(":")[1])
                    daten.append([sollwinkel, sollspannung, istspannung, istwinkel, 
                                  realwinkelmitte])
                except Exception as e:
                    print("Fehler beim Parsen:", e) #debug
                    continue
            elif line == 'READY':
                break
            elif line == 'CANCEL':
                break
            

        ser_Arduino.close()
        ser_Multi.close()

        if not stop_event.is_set():
            rows = []
            for(sollwinkel, sollspannung, istspannung, istwinkel, 
                                  realwinkelmitte), label in zip(daten, labels_iter):
                rows.append({
                    " ": label,
                    "Soll-Winkel [°]": round(sollwinkel, 1),
                    "Soll-Spannung [V]": round(sollspannung, 2),
                    "Ist-Spannung [V]": round(istspannung, 3),
                    "Ist-Winkel [°]": round(istwinkel, 1),
                    "Realer Winkel zur Mitte [°]": round(realwinkelmitte, 1),
                    #"Soll-Spannung Real [V]": round(realsollspannung, 3),
                    #"Linearität":  float(linear)
                })
            df = pd.DataFrame(rows)
            
            L = len(df)  # zur Sicherheit auf gleiche Länge bringen

            def round_sollReal(x): 
                return None if x is None else round(x, 3)

            def round_linear(x): 
                return None if x is None else float(x)

            df["Soll-Spannung Real [V]"] = [round_sollReal(v) for v in linear_sollV[:L]]
            df["Linearität"] = [round_linear(v) for v in linear_lin[:L]]

            path = r"C:\HSBI\Praktikum"
            book = load_workbook(path)
            with pd.ExcelWriter("RMTest-"+txt9.get()+".xlsx", engine="openpyxl") as writer:
                sheet = "Messung"
                df.to_excel(writer, index=False, sheet_name=sheet)
                wb = writer.book
                ws = writer.sheets[sheet]

                format_percent = wb.add_format({'num_format': '0.00%','align': 'center'})
                format_degree = wb.add_format({'num_format': '0.0°','align': 'center'})
                format_volt2 = wb.add_format({'num_format': '0.00','align': 'center'})
                format_volt3 = wb.add_format({'num_format': '0.000','align': 'center'})
                format_header = wb.add_format({'text_wrap': True, 'align': 'center', 'valign': 'vcenter', 'bold': True})
                format_error_percent = wb.add_format({'num_format': '0.00%', 'align': 'center', 'bg_color': "#F86A5A"})

                ws.set_row(0, 35, format_header)
                ws.set_column('A:A', 44)
                ws.set_column('B:B', 20, format_degree)
                ws.set_column('C:C', 20, format_volt2)
                ws.set_column('D:D', 20, format_volt3)
                ws.set_column('E:E', 20, format_degree)
                ws.set_column('F:F', 20, format_degree)
                ws.set_column('G:G', 20, format_volt3)
                ws.set_column('H:H', 20, format_percent)

                ws.freeze_panes(1,0)

                start = len(df) + 2  # 1 für Header + 1 Leerzeile

                # Fallbacks, falls nichts kam
                totzone   = summary_vals.get("Totzone")
                activeCW  = summary_vals.get("AktivCW")
                activeCCW = summary_vals.get("AktivCCW")
                activeSum = summary_vals.get("AktivSumme")

                ws.write(start + 0, 0, "Totzone")
                if totzone is not None:
                    ws.write_number(start + 0, 1, totzone, format_degree)

                ws.write(start + 1, 0, "Winkel Aktiver Bereich CW (Drehrichtung-)(11)")
                if activeCW is not None:
                    ws.write_number(start + 1, 1, activeCW, format_degree)

                ws.write(start + 2, 0, "Winkel Aktiver Bereich CCW (Drehrichtung+)(13)")
                if activeCCW is not None:
                    ws.write_number(start + 2, 1, activeCCW, format_degree)

                ws.write_blank(start + 3, 0, None)
                ws.write_blank(start + 3, 1, None)

                ws.write(start + 4, 0, "Aktive Bereiche Gesamt")
                if activeSum is not None:
                    ws.write_number(start + 4, 1, activeSum, format_degree)

                ws.write(start + 0, 6, "Lin Max")
                if lin_max is not None:
                    if error_lin_idx:
                        ws.write_number(start + 0, 7, lin_max, format_error_percent)
                    else:
                        ws.write_number(start + 0, 7, lin_max, format_percent)

                ws.write(start + 1, 6, "Lin Min")
                if lin_min is not None:
                    if error_lin_idx:
                        ws.write_number(start + 1, 7, lin_min, format_error_percent)
                    else:
                        ws.write_number(start + 1, 7, lin_min, format_percent)
                        
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

    root.after(0, on_finish)

'''
            with pd.ExcelWriter("RMTest-"+txt9.get()+".xlsx", engine="xlsxwriter") as writer:
                sheet = "Messung"
                df.to_excel(writer, index=False, sheet_name=sheet)
                wb = writer.book
                ws = writer.sheets[sheet]

                format_percent = wb.add_format({'num_format': '0.00%','align': 'center'})
                format_degree = wb.add_format({'num_format': '0.0°','align': 'center'})
                format_volt2 = wb.add_format({'num_format': '0.00','align': 'center'})
                format_volt3 = wb.add_format({'num_format': '0.000','align': 'center'})
                format_header = wb.add_format({'text_wrap': True, 'align': 'center', 'valign': 'vcenter', 'bold': True})
                format_error_percent = wb.add_format({'num_format': '0.00%', 'align': 'center', 'bg_color': "#F86A5A"})

                ws.set_row(0, 35, format_header)
                ws.set_column('A:A', 44)
                ws.set_column('B:B', 20, format_degree)
                ws.set_column('C:C', 20, format_volt2)
                ws.set_column('D:D', 20, format_volt3)
                ws.set_column('E:E', 20, format_degree)
                ws.set_column('F:F', 20, format_degree)
                ws.set_column('G:G', 20, format_volt3)
                ws.set_column('H:H', 20, format_percent)

                ws.freeze_panes(1,0)

                start = len(df) + 2  # 1 für Header + 1 Leerzeile

                # Fallbacks, falls nichts kam
                totzone   = summary_vals.get("Totzone")
                activeCW  = summary_vals.get("AktivCW")
                activeCCW = summary_vals.get("AktivCCW")
                activeSum = summary_vals.get("AktivSumme")

                ws.write(start + 0, 0, "Totzone")
                if totzone is not None:
                    ws.write_number(start + 0, 1, totzone, format_degree)

                ws.write(start + 1, 0, "Winkel Aktiver Bereich CW (Drehrichtung-)(11)")
                if activeCW is not None:
                    ws.write_number(start + 1, 1, activeCW, format_degree)

                ws.write(start + 2, 0, "Winkel Aktiver Bereich CCW (Drehrichtung+)(13)")
                if activeCCW is not None:
                    ws.write_number(start + 2, 1, activeCCW, format_degree)

                ws.write_blank(start + 3, 0, None)
                ws.write_blank(start + 3, 1, None)

                ws.write(start + 4, 0, "Aktive Bereiche Gesamt")
                if activeSum is not None:
                    ws.write_number(start + 4, 1, activeSum, format_degree)

                ws.write(start + 0, 6, "Lin Max")
                if lin_max is not None:
                    if error_lin_idx:
                        ws.write_number(start + 0, 7, lin_max, format_error_percent)
                    else:
                        ws.write_number(start + 0, 7, lin_max, format_percent)

                ws.write(start + 1, 6, "Lin Min")
                if lin_min is not None:
                    if error_lin_idx:
                        ws.write_number(start + 1, 7, lin_min, format_error_percent)
                    else:
                        ws.write_number(start + 1, 7, lin_min, format_percent)
                        
    except Exception as e:
        print("Fehler bei Serial: ", e) #debug

    root.after(0, on_finish)
'''

def close_window():
    root.destroy()

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
            ser_Arduino = open_first_available(("COM6","COM3"), baud=115200, timeout=5)
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

'''def goto():
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
        print("Fehler bei Serial: ", e) #debug'''

def go_zero(stop_event, on_finish):
    try:
        ser_Arduino = open_first_available(("COM6","COM3"), baud=115200, timeout=5)
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

# --------------- CALC BUTTON

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

    try:
        txtSoll = float(txt1.get().strip().replace(',', '.'))
        txtWinkel = float(txt6.get().strip().replace(',', '.'))
        txtDead11 = float(txt2.get().strip().replace(',', '.'))
        txtDead12 = float(txt3.get().strip().replace(',', '.'))
        txtDead21 = float(txt4.get().strip().replace(',', '.'))
        txtDead22 = float(txt5.get().strip().replace(',', '.'))
        txtDead31 = float(txt7.get().strip().replace(',', '.'))
        txtDead32 = float(txt8.get().strip().replace(',', '.'))
        
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
    threading.Thread(target=write_serial, args=(txtSoll, txtWinkel, txtDead11, txtDead12,
                                                 txtDead21, txtDead22, txtDead31, txtDead32,
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

# --------------- GUI

root = tk.Tk()
scrwid = root.winfo_screenwidth()
scrhei = root.winfo_screenheight()
root.geometry(f"{scrwid - scrwid//5}x{scrhei - scrhei//5}+0+0")
root.title("Test window")
root.resizable(False, False)


root.grid_columnconfigure(0, weight=0)
root.grid_columnconfigure(1, weight=1)
root.grid_rowconfigure(0, weight=0)
root.grid_rowconfigure(1, weight=1)

left_frame  = ttk.Frame(root)
right_frame = ttk.Frame(root)
left_frame.grid(row=1, column=0, sticky="nw", padx=12, pady=12)
right_frame.grid(row=1, column=1, sticky="nw",  padx=12, pady=12)

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

right_frame.grid_columnconfigure(0, weight=0)
right_frame.grid_columnconfigure(1, weight=0)

vcmd = (root.register(lambda P: (P.count(',') <= 1 and all(ch.isdigit() or ch == ',' for ch in P))), "%P")

ttk.Label(left_frame, text="Auftragsnummer:").grid(row=4, column=0, sticky="w", pady=(20, 0), padx=(20,0))
txt9 = ttk.Entry(left_frame, width=20)
txt9.grid(row=5, column=0, pady=(0, 10), padx=(20,0))

ttk.Label(right_frame, text="Sollspannung:").grid(row=1, column=1, sticky="w", pady=(40, 0), padx=(40,0))
txt1 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt1.grid(row=2, column=1, pady=(0, 10), padx=(40,0))
txt1.insert(0, "10,0")
txt1.focus_set()

ttk.Label(right_frame, text="Gesamtwinkel:").grid(row=1, column=2, sticky="w", pady=(40, 0), padx=(20,0))
txt6 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt6.grid(row=2, column=2, pady=(0, 10), padx=(20,0))
txt6.insert(0, "330,0")

ttk.Label(right_frame, text="Anfang Deadzone 1:").grid(row=3, column=1, sticky="w", pady=(10, 0), padx=(40,0))
txt2 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt2.grid(row=4, column=1, pady=(0, 10), padx=(40,0))
txt2.insert(0, "0,0")

ttk.Label(right_frame, text="Ende Deadzone 1:").grid(row=3, column=2, sticky="w", pady=(10, 0), padx=(20,0))
txt3 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt3.grid(row=4, column=2, pady=(0, 10), padx=(20,0))
txt3.insert(0, "40,0")

ttk.Label(right_frame, text="Anfang Deadzone 2:").grid(row=5, column=1, sticky="w", pady=(10, 0), padx=(40,0))
txt4 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt4.grid(row=6, column=1, pady=(0, 10), padx=(40,0))
txt4.insert(0, "140,0")

ttk.Label(right_frame, text="Ende Deadzone 2:").grid(row=5, column=2, sticky="w", pady=(10, 0), padx=(20,0))
txt5 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt5.grid(row=6, column=2, pady=(0, 10), padx=(20,0))
txt5.insert(0, "190,0")

ttk.Label(right_frame, text="Anfang Deadzone 3:").grid(row=7, column=1, sticky="w", pady=(10, 0), padx=(40,0))
txt7 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt7.grid(row=8, column=1, pady=(0, 10), padx=(40,0))
txt7.insert(0, "290,0")

ttk.Label(right_frame, text="Ende Deadzone 3:").grid(row=7, column=2, sticky="w", pady=(10, 0), padx=(20,0))
txt8 = ttk.Entry(right_frame, width=20, validate="key", validatecommand=vcmd)
txt8.grid(row=8, column=2, pady=(0, 10), padx=(20,0))
txt8.insert(0, "330,0")

#txtgo = ttk.Entry(left_frame, width=20, validate="key", validatecommand=vcmd)
#txtgo.grid(row=3, column=1, pady=(0, 0), padx=(0,0))

ttk.Button(left_frame, text="Abbrechen", command=close_window).grid(row=7, column=0, pady=(4, 5), padx=(0,0), ipadx=40)
ttk.Button(left_frame, text="Messen", command=open_calc_win).grid(row=6, column=0, pady=(80, 5), padx=(0,0), ipadx=40)
ttk.Button(left_frame, text="Position 0", command=open_zero_window).grid(row=8, column=0, pady=(80, 5), padx=(0,0), ipadx=40)
#ttk.Button(left_frame, text="0.1 Links", command=go_left).grid(row=6, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
#ttk.Button(left_frame, text="0.1 Rechts", command=go_Right).grid(row=7, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
#ttk.Button(left_frame, text="Conn Serial", command=ser_Connect).grid(row=5, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
#ttk.Button(left_frame, text="Curr Position", command=curr_Pos).grid(row=8, column=1, pady=(4, 5), padx=(0,0), ipadx=40)
#ttk.Button(left_frame, text="Go To", command=goto).grid(row=4, column=1, pady=(4, 5), padx=(0,0), ipadx=40)

txt1.bind("<Return>", lambda event: open_calc_win())
txt2.bind("<Return>", lambda event: open_calc_win())
txt3.bind("<Return>", lambda event: open_calc_win())
txt4.bind("<Return>", lambda event: open_calc_win())
txt5.bind("<Return>", lambda event: open_calc_win())
txt6.bind("<Return>", lambda event: open_calc_win())
txt7.bind("<Return>", lambda event: open_calc_win())
txt8.bind("<Return>", lambda event: open_calc_win())
root.bind("<Escape>", lambda event: close_window())

on_select_preset()
sv_ttk.set_theme("dark")
root.mainloop()