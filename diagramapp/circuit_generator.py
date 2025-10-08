import pandas as pd
import plotly.graph_objects as go

class DynamicCircuitDiagram:
    def __init__(self):
        #Define only colors here
        self.colors = {'SDA': '#0066cc','SCL': '#00ccff','SCLK': '#009900','MOSI': '#66ff66','MISO': '#006600','SS1': '#800080','SS2': '#9932CC',
            'TX': '#cc0000','RX': '#ff6600'
        }
        self.device_colors = {'Microcontroller': '#b3d9ff','I2C_Device': '#b3ffb3','SPI_Device': '#ffffb3','UART_Device': '#ffb3b3' }

    def read_excel_data(self, file_path):
        df = pd.read_excel(file_path)
        # convert "-" and NaN into empty string
        df = df.replace("-", "").fillna("")
        return df

    def create_chip(self, row):
        x, y = row["X"], row["Y"] 
        device_type = row["Device_Type"] 
        device_id = row["From_Device"] 
        address = row["Address"] 
        width, height = (80, 60) if device_type == "Microcontroller" else (40, 30) 
        shapes = [{ 'type': 'rect', 'x0': x - width/2, 'x1': x + width/2, 'y0': y - height/2, 'y1': y + height/2, 
                   'fillcolor': self.device_colors.get(device_type, 'lightgray'), 'line': {'color': 'black', 'width': 2} 
                }] 
        label = device_id 
        if address not in ["", "-"]:
            label += f" addr: {address}" 
        annotations = [{ 'x': x, 'y': y, 'text': label, 'showarrow': False, 'font': {'size': 11, 'color': 'black'}, 'align': 'center' }] 
        
        return shapes, annotations

    def add_free_arrows(self, df):
        """
        Reads Arrow_X, Arrow_Y, Direction, Arrow_Color from Excel
        and adds free-floating arrows (not tied to bus lines).
        """
        annotations = []

        # Only run if the required columns exist
        if not {"Arrow_X", "Arrow_Y"}.issubset(df.columns):
            return annotations

        for _, row in df.iterrows():
            if row["Arrow_X"] == "" or row["Arrow_Y"] == "":
                continue  # skip if missing values

            try:
                x = float(row["Arrow_X"])
                y = float(row["Arrow_Y"])
            except ValueError:
                continue  # skip if not numeric

            direction = str(row.get("Direction", "right")).lower()
            color = row.get("Arrow_Color", "black") if row.get("Arrow_Color", "") != "" else "black"

            # Arrow offset length
            shift = 20
            if direction == "right":
                ax, ay = x + shift, y
            elif direction == "left":
                ax, ay = x - shift, y
            elif direction == "up":
                ax, ay = x, y + shift   # FIXED
            elif direction == "down":
                ax, ay = x, y - shift   # FIXED
            else:
                ax, ay = x + shift, y  # default → right

            annotations.append(dict(
                x=ax, y=ay,
                ax=x, ay=y,
                xref="x", yref="y",
                axref="x", ayref="y",
                showarrow=True,
                arrowhead=3, arrowsize=1.5, arrowwidth=2,
                arrowcolor=color
            ))
        return annotations

    def connect_devices(self, df):
        traces, annotations = [], []
        device_positions = {row["From_Device"]: (row["X"], row["Y"]) for _, row in df.iterrows()}

        # --- PASS 1: record bus_y positions for extended buses ---
        bus_lines = {}  # {bus_label: y_coordinate}
        for _, row in df.iterrows():
            if "Bus_Label" in row and row["Bus_Label"] != "" and "Bus_Extend" in row and str(row["Bus_Extend"]).strip() != "":
                bus_labels = str(row["Bus_Label"]).split(",")
                from_x, from_y = device_positions[row["From_Device"]]

                # compute bus_y from Pin_Offset if present
                offset = int(row["Pin_Offset"]) if "Pin_Offset" in row and str(row["Pin_Offset"]).strip() != "" else 0
                bus_y = from_y + offset

                for bus in bus_labels:
                    bus_lines[bus.strip()] = bus_y

        # --- PASS 2: draw vertical connections from devices to buses ---
        for _, row in df.iterrows():
            buses = []
            styles = []
            
            if "Connect_To_Bus" in row and row["Connect_To_Bus"] != "":
                buses = str(row["Connect_To_Bus"]).split(",")

                if "Connect_To_Bus_Type" in row and row["Connect_To_Bus_Type"] != "":
                    styles = str(row["Connect_To_Bus_Type"]).split(",")
                else:
                    styles = ["dashed"] * len(buses)  # default style
            else:
                continue  # skip rows without vertical bus connections

            x, y = row["X"], row["Y"]

            # ✅ NEW: parse offsets if present
            x_offsets = []
            y_offsets = []
            if "Bus_X_Offset" in row and str(row["Bus_X_Offset"]).strip() != "":
                x_offsets = [int(v.strip()) for v in str(row["Bus_X_Offset"]).split(",")]
            if "Bus_Y_Offset" in row and str(row["Bus_Y_Offset"]).strip() != "":
                y_offsets = [int(v.strip()) for v in str(row["Bus_Y_Offset"]).split(",")]


            for i, bus in enumerate(buses):
                bus = bus.strip()
                if bus in bus_lines:
                    # use "solid" if defined, else default "dot"
                    line_style = "solid" if i < len(styles) and styles[i].strip().lower() == "solid" else "dot"

                    x_off = x_offsets[i] if i < len(x_offsets) else 0
                    y_off = y_offsets[i] if i < len(y_offsets) else 0

                    traces.append(go.Scatter(
                        x=[x + x_off, x + x_off],
                        y=[y + y_off, bus_lines[bus] + y_off],
                        mode="lines",
                        line=dict(color=self.colors.get(bus, "black"), width=2, dash=line_style),
                         showlegend=False
                    ))


        # --- PASS 3: normal device-to-device connections (unchanged) ---
        for device_name, group in df.groupby("From_Device"):
            if "Bus_Order" in group.columns:
                group = group.sort_values(by="Bus_Order")
        
            for _, row in group.iterrows():
                if row["To_Device"] == "" or row["Status"] != "active":
                    continue

                from_dev, to_dev = row["From_Device"], row["To_Device"]
                bus_labels = str(row["Bus_Label"]).split(",")
                from_x, from_y = device_positions[from_dev]
                to_x, to_y = device_positions[to_dev]

                spacing = 15
                for i, bus in enumerate(bus_labels):
                    if bus not in self.colors:
                        continue

                    if "Pin_Offset" in row and str(row["Pin_Offset"]).strip() != "":
                        offset = int(row["Pin_Offset"])
                    elif "Bus_Order" in row and str(row["Bus_Order"]).strip() != "":
                        offset = int(row["Bus_Order"]) * spacing
                    else:
                        offset = (i - len(bus_labels)//2) * spacing

                    bus_y = from_y + offset

                    # ✅ Pin_Side decides connection direction
                    pin_side = row.get("Pin_Side", "right")
                    if pin_side == "right":
                        start_x = from_x + 40
                        end_x = to_x - 40
                    elif pin_side == "left":
                        start_x = from_x - 40
                        end_x = to_x + 40
                    else:
                        start_x, end_x = from_x, to_x

                    if "Bus_Extend" in row and str(row["Bus_Extend"]).strip() != "":
                        end_x = from_x + int(row["Bus_Extend"])

                    traces.append(go.Scatter(x=[start_x, end_x],y=[bus_y, bus_y],mode="lines",line=dict(color=self.colors[bus], width=3),
                    name=bus,showlegend=True))

                    annotations.append({'x': (start_x + end_x) / 2,'y': bus_y + 10,'text': bus,'showarrow': False,'font': {'size': 10, 'color': self.colors[bus]}
                })
        return traces, annotations

    def generate_diagram(self, excel_file):
        df = self.read_excel_data(excel_file)

        fig = go.Figure()

        # Draw devices
        device_shapes, device_annotations = [], []
        for _, row in df.iterrows():
            shapes, ann = self.create_chip(row)
            device_shapes.extend(shapes)
            device_annotations.extend(ann)

        # Draw bus communication
        traces, comm_annotations = self.connect_devices(df)
        for t in traces:
            fig.add_trace(t)

        # 🔹 Add free arrows (independent of buses)
        free_arrow_annotations = self.add_free_arrows(df)

        fig.update_layout(
            title={'text': "Circuit Communication Diagram", 'x': 0.5},
            shapes=device_shapes,
            annotations=device_annotations + comm_annotations + free_arrow_annotations,
            showlegend=True,
            width=1200, height=800,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        return fig













# import pandas as pd
# import plotly.graph_objects as go

# class CircuitDiagramGenerator:
#     def __init__(self):
#         # Only define colors (rest is dynamic from Excel)
#         self.colors = {
#             'I2C': {'SDA': '#0066cc', 'SCL': '#00ccff'},
#             'SPI': {'SCLK': '#009900', 'MOSI': '#66ff66', 'MISO': '#006600', 'SS': '#800080'},
#             'UART': {'TX': '#cc0000', 'RX': '#ff6600'},
#             'protocol_bg': {'I2C': '#e6f3ff', 'SPI': '#e6ffe6', 'UART': '#ffe6e6'}
#         }

#         self.device_colors = {
#             'Microcontroller': '#b3d9ff',
#             'I2C_Device': '#b3ffb3',
#             'SPI_Device': '#ffffb3',
#             'UART_Device': '#ffb3b3'
#         }

#     def read_excel_data(self, file_path):
#         df = pd.read_excel(file_path, sheet_name=0)
#         df = df.replace("-", None).where(pd.notnull(df), None)
#         return df

#     def create_chip_shape(self, device):
#         x, y = device['X'], device['Y']
#         device_type = device['Device_Type']
#         device_id = device['From_Device']
#         address = device.get('Address', "")

#         width, height = (120, 100) if device_type == 'Microcontroller' else (80, 60)
#         shapes, annotations = [], []

#         # Chip body
#         shapes.append({
#             'type': 'rect',
#             'x0': x - width/2, 'x1': x + width/2,
#             'y0': y - height/2, 'y1': y + height/2,
#             'fillcolor': self.device_colors.get(device_type, 'lightgray'),
#             'line': {'color': 'black', 'width': 2}
#         })

#         # Label inside chip
#         label = device_id
#         if address: 
#             label += f"\naddr: {address}"

#         annotations.append({
#             'x': x, 'y': y,
#             'text': label,
#             'showarrow': False,
#             'font': {'size': 10, 'color': 'black'},
#             'align': 'center'
#         })

#         return shapes, annotations

#     def create_protocol_buses(self, df, device_positions):
#         traces, annotations = [], []
#         for _, row in df.iterrows():
#             if not row['Bus_Lines']:
#                 continue
#             buses = [b.strip() for b in str(row['Bus_Lines']).split(',')]
#             from_dev, to_dev = row['From_Device'], row['To_Device']
#             if from_dev not in device_positions:
#                 continue
#             x1, y1 = device_positions[from_dev]
#             if to_dev and to_dev in device_positions:
#                 x2, y2 = device_positions[to_dev]
#             else:
#                 x2, y2 = x1 + 200, y1  # default

#             for i, bus in enumerate(buses):
#                 bus_y = (y1 + y2)/2 + i*20
#                 color = self.colors.get(row['Protocol'], {}).get(bus, 'black')

#                 # Draw bus
#                 traces.append(go.Scatter(
#                     x=[x1, x2], y=[bus_y, bus_y],
#                     mode='lines',
#                     line=dict(color=color, width=3),
#                     name=bus,
#                     showlegend=True
#                 ))

#                 # Label bus
#                 annotations.append({
#                     'x': (x1 + x2)/2, 'y': bus_y + 10,
#                     'text': bus, 'showarrow': False,
#                     'font': {'size': 10, 'color': color}
#                 })

#         return traces, annotations

#     def generate_diagram(self, excel_file):
#         df = self.read_excel_data(excel_file)
#         fig = go.Figure()

#         # Positions map
#         device_positions = {row['From_Device']: (row['X'], row['Y']) for _, row in df.iterrows()}

#         # Device chips
#         shapes, annotations = [], []
#         for _, row in df.iterrows():
#             chip_shapes, chip_ann = self.create_chip_shape(row)
#             shapes.extend(chip_shapes)
#             annotations.extend(chip_ann)

#         # Protocol buses
#         traces, bus_ann = self.create_protocol_buses(df, device_positions)
#         for t in traces:
#             fig.add_trace(t)
#         annotations.extend(bus_ann)

#         fig.update_layout(
#             title={'text': "Dynamic Circuit Communication Diagram", 'x': 0.5},
#             showlegend=True,
#             width=1400, height=800,
#             shapes=shapes,
#             annotations=annotations,
#             xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
#             yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
#             plot_bgcolor='white',
#             paper_bgcolor='white'
#         )
#         return fig


