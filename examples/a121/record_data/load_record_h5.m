clear vars; close all; clc; format compact;

% Example MATLAB script to plot the A121 data in a h5-file
%
% Tested on MATLAB R2020b

filename = "datafile.h5";

% h5disp(filename) % Uncomment to see data file info

server_info = jsondecode(string(h5read(filename, "/server_info")));
session_config = jsondecode(string(h5read(filename, "/session/session_config")));
metadata =  jsondecode(string(h5read(filename, "/session/group_0/entry_0/metadata")));

disp("Data collected at = ");
disp(string(h5read(filename, "/timestamp")));

data = h5read(filename, "/session/group_0/entry_0/result/frame");
data = double(data.real) + 1i*double(data.imag); % (frame, sweep, depth)
disp("Loaded data size = ")
disp(size(data))

% Average all sweeps in one frame to a single sweep
data = mean(data, 2);
data = squeeze(data(:, 1, :));

sweep_info = session_config.groups.x1.subsweeps;  % Assuming only one subsweep
depths = sweep_info.start_point + sweep_info.step_length*(0:(sweep_info.num_points-1));
depths = depths*metadata.base_step_length_m;

time = double(h5read(filename, "/session/group_0/entry_0/result/tick"));
time = (time - time(1))/server_info.ticks_per_second;

plot_data = abs(data);
imagesc(time, depths, plot_data)
xlabel("Time [s]")
ylabel("Depth [m]")
sensor_id = num2str(h5read(filename, "/session/group_0/entry_0/sensor_id"));
title(strcat("Absolute value of SparseIQ data. Sensor id ", sensor_id))
