import pandas as pd
from bokeh.plotting import figure, show
from bokeh.models import Range1d, Label

def plot_digital_waveforms_bokeh(data, data_buses):
    try:
        required_columns = ["Time"] + data_buses  # Dynamic required columns
        for col in required_columns:
            if col not in data.columns:
                raise ValueError(f"Column '{col}' not found in the data.")

        time = data["Time"]
        num_time_points = len(time)

        num_buses = len(data_buses)  # Number of data buses

        p = figure(
            title="Digital Waveform Plot",
            x_range=Range1d(-1, num_time_points),
            y_range=(-1, 2 * num_buses - 1),  # Dynamic y-range
            x_axis_label="Time",
            width=1200, height=600
        )

        p.xgrid.grid_line_color = 'lightgray'
        p.background_fill_color = "white"

        for idx, bus_name in enumerate(data_buses):
            bus_data = data[bus_name]
            try:
                bus_data = pd.to_numeric(bus_data)
            except ValueError:
                bus_data = bus_data.apply(lambda x: 1 if 'D[A' in str(x) or str(x) == 'A' else 0)

            y_offset = 2 * idx
            y_values = [bus_data[i] + y_offset for i in range(num_time_points)]

            # Draw background patches
            for i in range(num_time_points):
                p.patch([i - 0.5, i + 0.5, i + 0.5, i - 0.5], [y_offset - 0.5, y_offset - 0.5, y_offset + 0.5, y_offset + 0.5], color="lightgray", alpha=0.5, line_width=0)

            # Draw Signal Lines
            for i in range(num_time_points - 1):
                x0 = i
                y0 = y_values[i]
                x1 = i + 1
                y1 = y_values[i]
                p.segment(x0=x0, y0=y0, x1=x1, y1=y1, color="black", line_width=2)
                if y_values[i] != y_values[i + 1]:
                    p.segment(x0=x1, y0=y0, x1=x1, y1=y_values[i + 1], color="black", line_width=2)

            # Add signal labels to the left
            label = Label(x=-0.7, y=y_offset, text=bus_name, x_offset=-10, y_offset=0, text_align="right")
            p.add_layout(label)

        p.xaxis.ticker = list(range(num_time_points))
        p.xaxis.major_label_overrides = {i: time[i] for i in range(num_time_points)}
        p.yaxis.major_tick_line_color = None
        p.yaxis.minor_tick_line_color = None
        p.yaxis.major_label_text_font_size = '0pt'
        p.yaxis.axis_line_color = None

        show(p)

    except Exception as e:
        print(f"An error occurred during plotting: {e}")

if __name__ == "__main__":  # Corrected the name to __name__
    file_path = "temp_test/Waveform_create_Andgate.xls"
    data_buses = ["ACLK", "ARADDR", "ARVALID", "ARREADY", "RDATA", "RLAST", "RVALID", "RREADY"]  # Define your data buses here
    try:
        data = pd.read_excel(file_path, engine='xlrd')
        plot_digital_waveforms_bokeh(data, data_buses)  # Pass data_buses to the function
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}. Please check the path.")
    except pd.errors.ParserError:
        print(f"Error: Could not parse the Excel file at {file_path}. Check file format or contents.")
    except Exception as e:
        print(f"An unexpected error occurred during file processing: {e}")
