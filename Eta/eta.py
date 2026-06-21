import sys
import datetime
import requests
import curses

TIMEOUT = 5
KMB_BASE = "https://data.etabus.gov.hk/v1/transport/kmb"
CTB_BASE = "https://rt.data.gov.hk/v2/transport/citybus"
NLB_BASE = "https://rt.data.gov.hk/v2/transport/nlb"

class BusTracker:
    def __init__(self):
        self.operator = None     
        self.route = None
        self.direction = None    
        self.service_type = "1"  
        self.stops = []          
        self.selected_stop = None
        self.scroll_index = 0

    def fetch_json(self, url):
        try:
            res = requests.get(url, timeout=TIMEOUT)
            res.raise_for_status()
            return res.json().get("data", []) or res.json()
        except Exception:
            return None

    def calculate_mins(self, eta_time_str):
        if not eta_time_str:
            return "無班次資料"
        try:
            eta_time = datetime.datetime.fromisoformat(eta_time_str)
            now = datetime.datetime.now(datetime.timezone.utc)
            diff = int((eta_time - now).total_seconds() / 60)
            return f"{diff} 分鐘" if diff > 0 else "正在抵達"
        except Exception:
            return "未知"

    def get_input_string(self, stdscr, prompt_text, y, x):
        """A safe input utility rendering natively within active viewport lines."""
        curses.echo()
        stdscr.addstr(y, x, prompt_text)
        stdscr.refresh()
        input_bytes = stdscr.getstr(y, x + len(prompt_text))
        curses.noecho()
        return input_bytes.decode('utf-8').strip()

    def draw_layout_bar(self, stdscr, max_y, max_x):
        """Forces the horizontal bar and text options directly onto terminal boundary rows."""
        try:
            stdscr.addstr(max_y - 3, 0, "-" * (max_x - 1))
            stdscr.addstr(max_y - 2, 0, "[q] 離開  [b] 返回  [r] 重新整理", curses.A_BOLD)
        except curses.error:
            pass

    def main_loop(self, stdscr):
        curses.curs_set(1)  # Enable visible tracking line cursors
        state = "OPERATOR"
        
        while True:
            stdscr.clear()
            max_y, max_x = stdscr.getmaxyx()
            self.draw_layout_bar(stdscr, max_y, max_x)

            if state == "OPERATOR":
                stdscr.addstr(0, 0, "1: KMB\n2: CTB\n3: NLB")
                choice = self.get_input_string(stdscr, "> ", 4, 0).lower()
                
                if choice == 'q': break
                elif choice == '1': self.operator, state = "KMB", "ROUTE"
                elif choice == '2': self.operator, state = "CTB", "ROUTE"
                elif choice == '3': self.operator, state = "NLB", "ROUTE"

            elif state == "ROUTE":
                stdscr.addstr(0, 0, f"巴士公司: {self.operator}")
                prompt = "輸入路線編號 [例如 1A / 102 ] > "
                choice = self.get_input_string(stdscr, prompt, 2, 0)
                
                if choice.lower() == 'q': break
                if choice.lower() == 'b': state = "OPERATOR"; continue
                if choice:
                    self.route = choice.upper()
                    state = "DIRECTION"

            elif state == "DIRECTION":
                stdscr.addstr(0, 0, f"{self.operator} {self.route}\n\n1: 去程\n2: 回程")
                choice = self.get_input_string(stdscr, "> ", 5, 0).lower()
                
                if choice == 'q': break
                if choice == 'b': state = "ROUTE"; continue
                if choice in ['1', '2']:
                    if self.operator in ["KMB", "CTB"]:
                        self.direction = "outbound" if choice == '1' else "inbound"
                    elif self.operator == "NLB":
                        self.direction = "O" if choice == '1' else "I"
                    
                    stdscr.addstr(7, 0, "載入中...")
                    stdscr.refresh()
                    self.load_stations()
                    self.scroll_index = 0
                    state = "STATIONS"

            elif state == "STATIONS":
                dir_label = "去程" if self.direction in ["outbound", "O"] else "回程"
                stdscr.addstr(0, 0, f"{self.operator} {self.route} ({dir_label})")
                
                if not self.stops:
                    stdscr.addstr(2, 0, "無車站資料，請確認路線是否正確。")
                    choice = self.get_input_string(stdscr, "> ", 4, 0).lower()
                    if choice == 'b': state = "DIRECTION"
                    elif choice == 'q': break
                    continue

                # Scroll bounding block equations mapping logic lines
                usable_height = max_y - 6  # Reserve lines safely for menu overlays
                visible_stops = self.stops[self.scroll_index : self.scroll_index + usable_height]
                
                for i, stop in enumerate(visible_stops):
                    line_num = self.scroll_index + i + 1
                    stdscr.addstr(2 + i, 0, f"{line_num}: {stop['name']}")

                # Render positional page counts above line border paths
                if len(self.stops) > usable_height:
                    stdscr.addstr(max_y - 4, 0, f"[提示] 可輸入 w 上捲 / s 下捲 瀏覽更多車站")

                choice = self.get_input_string(stdscr, "輸入車站號碼 > ", max_y - 1, 0).lower()
                
                if choice == 'q': break
                elif choice == 'b': state = "DIRECTION"; self.stops = []; continue
                elif choice == 'r': self.load_stations(); continue
                elif choice == 'w': # Scroll screen view up
                    self.scroll_index = max(0, self.scroll_index - usable_height)
                elif choice == 's': # Scroll screen view down
                    if self.scroll_index + usable_height < len(self.stops):
                        self.scroll_index += usable_height
                elif choice.isdigit() and 1 <= int(choice) <= len(self.stops):
                    self.selected_stop = self.stops[int(choice) - 1]
                    state = "ETA"

            elif state == "ETA":
                stdscr.addstr(0, 0, f"{self.operator} {self.route} -> {self.selected_stop['name']}\n")
                
                # Fetch live data strings directly into buffer array tracking matrices
                lines = self.get_eta_lines()
                for idx, line in enumerate(lines):
                    stdscr.addstr(2 + idx, 0, line)
                
                choice = self.get_input_string(stdscr, "> ", max_y - 1, 0).lower()
                if choice == 'q': break
                elif choice == 'b': state = "STATIONS"; continue
                elif choice == 'r': continue

    def load_stations(self):
        self.stops = []
        if self.operator == "KMB":
            layout_url = f"{KMB_BASE}/route-stop/{self.route}/{self.direction}/{self.service_type}"
            raw_layout = self.fetch_json(layout_url) or []
            if not isinstance(raw_layout, list): return

            for s in raw_layout:
                if isinstance(s, dict):
                    sid = s.get("stop")
                    name_data = self.fetch_json(f"{KMB_BASE}/stop/{sid}")
                    sname = name_data.get("name_tc", sid) if isinstance(name_data, dict) else sid
                    self.stops.append({"id": sid, "name": sname})

        elif self.operator == "CTB":
            layout_url = f"{CTB_BASE}/route-stop/ctb/{self.route}/{self.direction}"
            raw_layout = self.fetch_json(layout_url) or []
            if not isinstance(raw_layout, list): return

            for s in raw_layout:
                if isinstance(s, dict):
                    sid = s.get("stop")
                    sname = s.get("name_tc") or s.get("stop_name", sid)
                    self.stops.append({"id": sid, "name": sname})

        elif self.operator == "NLB":
            routes = self.fetch_json(f"{NLB_BASE}/route").get("routes", []) if self.fetch_json(f"{NLB_BASE}/route") else []
            rid = next((r["routeId"] for r in routes if isinstance(r, dict) and r.get("routeNo") == self.route), None)
            if rid:
                raw_stops = self.fetch_json(f"{NLB_BASE}/stop?routeId={rid}").get("stops", []) if self.fetch_json(f"{NLB_BASE}/stop?routeId={rid}") else []
                for s in raw_stops:
                    if isinstance(s, dict):
                        self.stops.append({"id": s.get("stopId"), "name": s.get("stopName_c")})

    def get_eta_lines(self):
        output = []
        sid = self.selected_stop["id"]
        if self.operator == "KMB":
            records = self.fetch_json(f"{KMB_BASE}/stop-eta/{sid}") or []
            matched = [r for r in records if isinstance(r, dict) and r.get("route") == self.route and str(r.get("dir")).lower() == self.direction[0]]
            for idx, r in enumerate(matched[:3]):
                output.append(f"巴士 {idx+1}: {self.calculate_mins(r.get('eta'))} ({r.get('rmk_tc', '即時班次')})")

        elif self.operator == "CTB":
            records = self.fetch_json(f"{CTB_BASE}/eta/ctb/{sid}/{self.route}") or []
            matched = [r for r in records if isinstance(r, dict) and str(r.get("dir")).upper() == self.direction.upper()]
            for idx, r in enumerate(matched[:3]):
                output.append(f"巴士 {idx+1}: {self.calculate_mins(r.get('eta'))} ({r.get('rmk_tc', '即時班次')})")

        elif self.operator == "NLB":
            routes = self.fetch_json(f"{NLB_BASE}/route").get("routes", []) if self.fetch_json(f"{NLB_BASE}/route") else []
            rid = next((r["routeId"] for r in routes if isinstance(r, dict) and r.get("routeNo") == self.route), None)
            if rid:
                records = self.fetch_json(f"{NLB_BASE}/eta?routeId={rid}&stopId={sid}").get("estimatedArrivals", [])
                for idx, r in enumerate(records[:3]):
                    if isinstance(r, dict):
                        output.append(f"巴士 {idx+1}: {r.get('estimatedArrivalTime')}")
        if not output:
            output.append("暫無即時班次資料")
        return output

if __name__ == "__main__":
    # curses.wrapper dynamically creates and cleans the alternative viewport layout completely on exit
    tracker = BusTracker()
    curses.wrapper(tracker.main_loop)
