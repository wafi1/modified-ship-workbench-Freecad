# -*- coding: utf-8 -*-
"""
StabilityMonitor.py - KORRIGIERTE VERSION mit Heel-Limits
"""

import FreeCAD as App
import math
from PySide import QtGui, QtCore


def _get_float(lc, cell, default=None):
    try:
        v = lc.get(cell)
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            v = v.strip()
            if v in ("", "-") or "[" in v:
                return default
            return float(v)
        return default
    except (ValueError, TypeError):
        return default


def _read_loadcondition():
    """Liest LoadCondition und berechnet alle Werte"""
    doc = App.activeDocument()
    if not doc:
        return None, None

    # Finde LoadCondition
    lc = None
    for obj in doc.Objects:
        if obj.TypeId == "Spreadsheet::Sheet":
            n = (obj.Label + obj.Name).replace(" ", "").replace("_", "").lower()
            if "loadcondition" in n:
                lc = obj
                break
    
    if not lc:
        return None, None

    # Lese Werte aus LoadCondition
    data = {}
    data['total_mass_kg'] = _get_float(lc, 'D4', 0)
    data['draft'] = _get_float(lc, 'E4') or _get_float(lc, 'D6')
    data['kmt'] = _get_float(lc, 'F4')
    data['gmt'] = _get_float(lc, 'G4')
    data['lcg'] = _get_float(lc, 'E5')
    data['tcg'] = _get_float(lc, 'F5')
    data['vcg'] = _get_float(lc, 'G5')
    
    total_mass_t = data['total_mass_kg'] / 1000.0
    
    # LADE HYDROSTATIK UND BERECHNE TRIM
    hydro_data = _load_and_calculate(doc, total_mass_t, data['lcg'], data['draft'])
    
    if hydro_data:
        data.update(hydro_data)
    else:
        data['lcb'] = None
        data['trim_cm'] = None
        data['trim_deg'] = None
        data['draft_aft'] = None
        data['draft_fwd'] = None

    return lc, data


def _load_and_calculate(doc, mass_t, lcg, mean_draft):
    """
    Lädt Hydrostatik, interpoliert und berechnet Trim und Drafts.
    Exakt die gleiche Logik wie das Diagnose-Skript.
    """
    if lcg is None or mass_t <= 0:
        return None
    
    # Finde Hydrostatics
    hydro = None
    for obj in doc.Objects:
        if obj.TypeId == "Spreadsheet::Sheet":
            if "hydro" in obj.Label.lower():
                hydro = obj
                break
    
    if not hydro:
        return None
    
    # Lese alle Punkte
    points = []
    row = 2
    while True:
        try:
            disp_t = float(hydro.get(f'A{row}'))
            draft = float(hydro.get(f'B{row}'))
            tmc = float(hydro.get(f'D{row}') or 0)
            lcb = float(hydro.get(f'F{row}') or 0)
            points.append((disp_t, draft, tmc, lcb))
            row += 1
        except:
            break
    
    if len(points) < 2:
        return None
    
    # Interpolation (identisch zum Diagnose-Skript)
    if mass_t <= points[0][0]:
        p = points[0]
    elif mass_t >= points[-1][0]:
        p = points[-1]
    else:
        for i in range(len(points) - 1):
            if points[i][0] <= mass_t <= points[i+1][0]:
                f = (mass_t - points[i][0]) / (points[i+1][0] - points[i][0])
                p = (
                    mass_t,
                    points[i][1] + f * (points[i+1][1] - points[i][1]),
                    points[i][2] + f * (points[i+1][2] - points[i][2]),
                    points[i][3] + f * (points[i+1][3] - points[i][3]),
                )
                break
        else:
            p = points[-1]
    
    # Berechne Trim
    delta_x = lcg - p[3]  # LCG - LCB
    trim_cm = 0.0
    
    if p[2] > 0:  # TMC > 0
        trim_cm = (delta_x * mass_t) / p[2]
    
    # Berechne Drafts
    trim_m = trim_cm / 100.0
    draft_aft = mean_draft - trim_m / 2
    draft_fwd = mean_draft + trim_m / 2
    
    return {
        'lcb': p[3],
        'tmc': p[2],
        'trim_cm': trim_cm,
        'draft_aft': draft_aft,
        'draft_fwd': draft_fwd,
    }


def _calculate_heel(tcg, gm):
    if not tcg or not gm or gm <= 0:
        return None
    ratio = tcg / gm
    if abs(ratio) > 1.0:
        return math.copysign(999.0, ratio)
    return math.degrees(math.asin(ratio))


class StabilityMonitor(QtGui.QWidget):
    WARN_HEEL = 3.0   # Ab hier Hintergrund rot
    MAX_HEEL = 5.0    # Ab hier Anzeige "n.a."

    def __init__(self, parent=None):
        super().__init__(parent,
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Tool)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setMinimumWidth(260)
        self._drag_pos = None

        self._build_ui()
        self._build_timer()
        self.refresh()

    def _build_ui(self):
        outer = QtGui.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QtGui.QFrame()
        self._card.setObjectName("card")
        self._card.setStyleSheet("""
            QFrame#card {
                background: rgba(30,30,40,210);
                border: 1px solid #555;
                border-radius: 10px;
            }
        """)

        main = QtGui.QVBoxLayout(self._card)
        main.setContentsMargins(12, 8, 12, 10)
        main.setSpacing(6)

        # Titel
        title_row = QtGui.QHBoxLayout()
        title_lbl = QtGui.QLabel("⚓ Stability Monitor")
        title_lbl.setStyleSheet("color:#aac; font-size:11px; font-weight:bold;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        refresh_btn = QtGui.QPushButton("↻")
        refresh_btn.setFixedSize(22, 22)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.setStyleSheet(
            "QPushButton{color:#aac;background:transparent;border:none;"
            "font-size:14px;} QPushButton:hover{color:white;}")
        refresh_btn.clicked.connect(self.refresh)
        title_row.addWidget(refresh_btn)

        close_btn = QtGui.QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton{color:#888;background:transparent;border:none;"
            "font-size:11px;} QPushButton:hover{color:#f88;}")
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)
        main.addLayout(title_row)

        # Heel
        self._heel_frame = QtGui.QFrame()
        self._heel_frame.setObjectName("heelframe")
        self._heel_frame.setStyleSheet("""
            QFrame#heelframe {
                background: rgba(50,50,70,180);
                border-radius: 7px;
                padding: 4px;
            }
        """)
        heel_layout = QtGui.QVBoxLayout(self._heel_frame)
        heel_layout.setContentsMargins(8, 6, 8, 6)
        heel_layout.setSpacing(2)

        heel_title = QtGui.QLabel("Heel Angle")
        heel_title.setStyleSheet("color:#99aacc; font-size:10px;")
        heel_layout.addWidget(heel_title, alignment=QtCore.Qt.AlignLeft)

        self._heel_value = QtGui.QLabel("— °")
        self._heel_value.setStyleSheet(
            "color:white; font-size:28px; font-weight:bold;")
        self._heel_value.setAlignment(QtCore.Qt.AlignCenter)
        heel_layout.addWidget(self._heel_value)

        self._heel_note = QtGui.QLabel("")
        self._heel_note.setStyleSheet("color:#cc8; font-size:9px;")
        self._heel_note.setAlignment(QtCore.Qt.AlignCenter)
        self._heel_note.setWordWrap(True)
        heel_layout.addWidget(self._heel_note)

        main.addWidget(self._heel_frame)

        # Draft & Trim
        draft_frame = QtGui.QFrame()
        draft_frame.setStyleSheet(
            "background:rgba(40,40,55,160); border-radius:5px;")
        draft_layout = QtGui.QGridLayout(draft_frame)
        draft_layout.setContentsMargins(8, 6, 8, 6)
        draft_layout.setSpacing(4)

        style_label = "color:#99aacc; font-size:9px;"
        style_value = "color:white; font-size:11px; font-weight:bold;"
        style_sub = "color:#aaa; font-size:8px;"

        draft_layout.addWidget(self._lbl("Mean Draft", style_label), 0, 0)
        self._draft_mean = self._lbl("—", style_value)
        draft_layout.addWidget(self._draft_mean, 0, 1)
        draft_layout.addWidget(self._lbl("m", style_sub), 0, 2)

        draft_layout.addWidget(self._lbl("Trim", style_label), 1, 0)
        self._trim_val = self._lbl("—", style_value)
        draft_layout.addWidget(self._trim_val, 1, 1)
        draft_layout.addWidget(self._lbl("cm", style_sub), 1, 2)

        draft_layout.addWidget(self._lbl("Draft Aft", style_label), 2, 0)
        self._draft_aft = self._lbl("—", style_value)
        draft_layout.addWidget(self._draft_aft, 2, 1)
        draft_layout.addWidget(self._lbl("m", style_sub), 2, 2)

        draft_layout.addWidget(self._lbl("Draft Fwd", style_label), 3, 0)
        self._draft_fwd = self._lbl("—", style_value)
        draft_layout.addWidget(self._draft_fwd, 3, 1)
        draft_layout.addWidget(self._lbl("m", style_sub), 3, 2)

        main.addWidget(draft_frame)

        # Stabilität
        stab_frame = QtGui.QFrame()
        stab_frame.setStyleSheet(
            "background:rgba(35,35,50,160); border-radius:5px;")
        stab_layout = QtGui.QVBoxLayout(stab_frame)
        stab_layout.setContentsMargins(8, 6, 8, 6)
        stab_layout.setSpacing(2)

        self._gm_label = self._lbl("GMt: —", "color:#99aacc; font-size:9px;")
        stab_layout.addWidget(self._gm_label)

        self._lcb_lcg_label = self._lbl("LCB/LCG: —", "color:#778; font-size:8px;")
        stab_layout.addWidget(self._lcb_lcg_label)

        main.addWidget(stab_frame)

        # Status
        self._status_lbl = self._lbl("—", "color:#556; font-size:8px;")
        main.addWidget(self._status_lbl)

        outer.addWidget(self._card)
        self.setLayout(outer)

    @staticmethod
    def _lbl(text, style=""):
        l = QtGui.QLabel(text)
        if style:
            l.setStyleSheet(style)
        return l

    def _build_timer(self):
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def refresh(self):
        lc, data = _read_loadcondition()
        
        if not lc or not data:
            self._set_heel_display(None, 0, 0)
            self._status_lbl.setText("⚠ No data")
            return

        # Heel
        tcg = data.get('tcg', 0)
        gm = data.get('gmt', 0)
        heel = _calculate_heel(tcg, gm)
        self._set_heel_display(heel, tcg, gm)

        # Draft
        draft = data.get('draft')
        if draft:
            self._draft_mean.setText(f"{draft:.2f}")
        else:
            self._draft_mean.setText("—")

        # Trim
        trim_cm = data.get('trim_cm')
        if trim_cm is not None:
            sign = "+" if trim_cm > 0 else ""
            self._trim_val.setText(f"{sign}{trim_cm:.1f}")
            
            if abs(trim_cm) > 50:
                self._trim_val.setStyleSheet("color:#f88; font-size:11px; font-weight:bold;")
            else:
                self._trim_val.setStyleSheet("color:#7f7; font-size:11px; font-weight:bold;")
        else:
            self._trim_val.setText("—")

        # Draft Aft/Fwd
        da = data.get('draft_aft')
        df = data.get('draft_fwd')
        if da is not None and df is not None:
            self._draft_aft.setText(f"{da:.2f}")
            self._draft_fwd.setText(f"{df:.2f}")
        else:
            self._draft_aft.setText("—")
            self._draft_fwd.setText("—")

        # Stabilität
        gm_val = data.get('gmt')
        if gm_val is not None:
            color = "#7f7" if gm_val > 0.5 else "#cc8" if gm_val > 0.15 else "#f88"
            self._gm_label.setStyleSheet(f"color:{color}; font-size:9px;")
            self._gm_label.setText(f"GMt: {gm_val:.3f} m")
        else:
            self._gm_label.setText("GMt: —")

        lcb = data.get('lcb')
        lcg = data.get('lcg')
        if lcb is not None and lcg is not None:
            self._lcb_lcg_label.setText(f"LCB: {lcb:.2f}m | LCG: {lcg:.2f}m")
        else:
            self._lcb_lcg_label.setText("LCB/LCG: —")

        # Status
        mass_t = data.get('total_mass_kg', 0) / 1000.0
        self._status_lbl.setText(
            f"Mass: {mass_t:.1f}t | {QtCore.QTime.currentTime().toString('hh:mm:ss')}")

    def _set_heel_display(self, heel_deg, tcg, gm):
        if heel_deg is None:
            self._heel_value.setText("— °")
            self._heel_note.setText("No heel data")
            self._heel_frame.setStyleSheet("""
                QFrame#heelframe {
                    background: rgba(50,50,70,180);
                    border-radius: 7px; padding: 4px;
                }""")
            return

        abs_heel = abs(heel_deg)
        
        # NEU: Ab MAX_HEEL (5°) -> n.a. anzeigen
        if abs_heel >= self.MAX_HEEL:
            self._heel_value.setText("n.a.")
            self._heel_value.setStyleSheet(
                "color:#f88; font-size:28px; font-weight:bold;")  # Rot
            self._heel_note.setText(f"⚠ Heel ≥ {self.MAX_HEEL}° — Limit überschritten!")
            bg = "rgba(200,0,0,230)"  # Roter Hintergrund
        elif abs_heel >= self.WARN_HEEL:
            # Ab WARN_HEEL (3°) -> Roter Hintergrund, aber Wert anzeigen
            if heel_deg < 0:
                direction = "→ STB"
            elif heel_deg > 0:
                direction = "← BB"
            else:
                direction = "even"
            self._heel_value.setText(f"{heel_deg:+.1f}° {direction}")
            self._heel_value.setStyleSheet(
                "color:white; font-size:28px; font-weight:bold;")
            self._heel_note.setText(f"⚠ Heel ≥ {self.WARN_HEEL}° — Achtung!")
            bg = "rgba(200,0,0,230)"  # Roter Hintergrund
        elif heel_deg < 0:
            direction = "→ STB"
            self._heel_value.setText(f"{heel_deg:+.1f}° {direction}")
            self._heel_value.setStyleSheet(
                "color:white; font-size:28px; font-weight:bold;")
            self._heel_note.setText(f"TCG={tcg:.3f}m GM={gm:.2f}m")
            bg = "rgba(30,60,40,180)"  # Grün
        elif heel_deg > 0:
            direction = "← BB"
            self._heel_value.setText(f"{heel_deg:+.1f}° {direction}")
            self._heel_value.setStyleSheet(
                "color:white; font-size:28px; font-weight:bold;")
            self._heel_note.setText(f"TCG={tcg:.3f}m GM={gm:.2f}m")
            bg = "rgba(30,60,40,180)"  # Grün
        else:
            self._heel_value.setText("0.0° even")
            self._heel_value.setStyleSheet(
                "color:white; font-size:28px; font-weight:bold;")
            self._heel_note.setText(f"TCG={tcg:.3f}m GM={gm:.2f}m")
            bg = "rgba(30,60,40,180)"  # Grün

        self._heel_frame.setStyleSheet(f"""
            QFrame#heelframe {{
                background: {bg};
                border-radius: 7px;
                padding: 4px;
            }}""")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = (event.globalPos() - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, event):
        if (event.buttons() == QtCore.Qt.LeftButton and self._drag_pos is not None):
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


_monitor_instance = None

def show_stability_monitor():
    global _monitor_instance
    if _monitor_instance is not None:
        try:
            _monitor_instance.close()
        except Exception:
            pass
    _monitor_instance = StabilityMonitor()
    _monitor_instance.move(100, 100)
    _monitor_instance.show()
    return _monitor_instance


__all__ = ['StabilityMonitor', 'show_stability_monitor']
