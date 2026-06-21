import sys
import datetime
import requests

TIMEOUT = 5
KMB_BASE = "https://data.etabus.gov.hk/v1/transport/kmb"
CTB_BASE = "https://rt.data.gov.hk/v2/transport/citybus"
NLB_BASE = "https://rt.data.gov.hk/v2/transport/nlb"

class BusTracker:
    def __init__(self):
        self.state = "OPERATOR"  
        self.operator = None     
        self.route = None
        self.direction = None    
        self.service_type = "1"  
        self.stops = []          
        self.selected_stop = None

    def draw_screen(self, print_body_func, custom_prompt="> "):
        """Clears current view and purges terminal scrollback history buffer completely."""
        # \033[2J clear screen, \033[3J clears scrollback history, \033[H resets cursor
        sys.stdout.write("\033[2J\033[3J\033[H")
        
        print_body_func()
        
        print("-" * 30)
        print("\033[1;36m[q] 離開  [b] 返回  [r] 重新整理\033[0m")
        sys.stdout.write(f"\n{custom_prompt}")
        sys.stdout.flush()

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

    def run(self):
        while True:
            if self.state == "OPERATOR":
                def view():
                    print("1: KMB\n2: CTB\n3: NLB")
                self.draw_screen(view)
                
                choice = input().strip().lower()
                if choice == 'q': break
                elif choice == '1': self.operator, self.state = "KMB", "ROUTE"
                elif choice == '2': self.operator, self.state = "CTB", "ROUTE"
                elif choice == '3': self.operator, self.state = "NLB", "ROUTE"

            elif self.state == "ROUTE":
                def view():
                    print(f"巴士公司: {self.operator}")
                
                prompt_text = f"輸入路線編號 [例如 1A / 102 / 968 ] > "
                self.draw_screen(view, custom_prompt=prompt_text)
                
                self.route = input().strip().upper()
                if self.route.lower() == 'q': break
                if self.route.lower() == 'b': self.state = "OPERATOR"; continue
                self.state = "DIRECTION"

            elif self.state == "DIRECTION":
                def view():
                    print(f"{self.operator} {self.route}\n")
                    print("1: 去程\n2: 回程")
                self.draw_screen(view)
                
                choice = input().strip().lower()
                if choice == 'q': break
                if choice == 'b': self.state = "ROUTE"; continue
                
                if choice in ['1', '2']:
                    if self.operator in ["KMB", "CTB"]:
                        self.direction = "outbound" if choice == '1' else "inbound"
                    elif self.operator == "NLB":
                        self.direction = "O" if choice == '1' else "I"
                    
                    self.load_stations()
                    self.state = "STATIONS"

            elif self.state == "STATIONS":
                def view():
                    dir_label = "去程" if self.direction in ["outbound", "O"] else "回程"
                    print(f"{self.operator} {self.route} ({dir_label})\n")
                    
                    if not self.stops:
                        print("無車站資料，請確認路線和方向是否正確。")
                        return

                    for idx, stop in enumerate(self.stops):
                        print(f"{idx + 1}: {stop['name']}")
                        
                self.draw_screen(view, custom_prompt="輸入車站號碼 > ")

                if not self.stops:
                    input()
                    self.state = "DIRECTION"
                    continue
                
                choice = input().strip().lower()
                if choice == 'q': break
                if choice == 'b': self.state = "DIRECTION"; self.stops = []; continue
                if choice == 'r': self.load_stations(); continue

                if choice.isdigit() and 1 <= int(choice) <= len(self.stops):
                    self.selected_stop = self.stops[int(choice) - 1]
                    self.state = "ETA"

            elif self.state == "ETA":
                def view():
                    print(f"{self.operator} {self.route} -> {self.selected_stop['name']}\n")
                    self.show_live_eta()
                self.draw_screen(view)
                
                choice = input().strip().lower()
                if choice == 'q': break
                if choice == 'b': self.state = "STATIONS"; continue
                if choice == 'r': continue

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

    def show_live_eta(self):
        sid = self.selected_stop["id"]
        if self.operator == "KMB":
            records = self.fetch_json(f"{KMB_BASE}/stop-eta/{sid}") or []
            matched = [r for r in records if isinstance(r, dict) and r.get("route") == self.route and str(r.get("dir")).lower() == self.direction[0]]
            for idx, r in enumerate(matched[:3]):
                print(f"巴士 {idx+1}: {self.calculate_mins(r.get('eta'))} ({r.get('rmk_tc', '即時班次')})")

        elif self.operator == "CTB":
            records = self.fetch_json(f"{CTB_BASE}/eta/ctb/{sid}/{self.route}") or []
            matched = [r for r in records if isinstance(r, dict) and str(r.get("dir")).upper() == self.direction.upper()]
            for idx, r in enumerate(matched[:3]):
                print(f"巴士 {idx+1}: {self.calculate_mins(r.get('eta'))} ({r.get('rmk_tc', '即時班次')})")

        elif self.operator == "NLB":
            routes = self.fetch_json(f"{NLB_BASE}/route").get("routes", []) if self.fetch_json(f"{NLB_BASE}/route") else []
            rid = next((r["routeId"] for r in routes if isinstance(r, dict) and r.get("routeNo") == self.route), None)
            if rid:
                records = self.fetch_json(f"{NLB_BASE}/eta?routeId={rid}&stopId={sid}").get("estimatedArrivals", [])
                for idx, r in enumerate(records[:3]):
                    if isinstance(r, dict):
                        print(f"巴士 {idx+1}: {r.get('estimatedArrivalTime')}")

if __name__ == "__main__":
    try:
        tracker = BusTracker()
        tracker.run()
        sys.stdout.write("\033[2J\033[3J\033[H")
    except KeyboardInterrupt:
        sys.stdout.write("\033[2J\033[3J\033[H")
