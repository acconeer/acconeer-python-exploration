clear vars; close all; clc; format compact;

filename = "data.h5";
info = h5info(filename);

disp("Keys =")
for i = 1:size(info.Datasets)
    name = info.Datasets(i).Name;
    fprintf("  %s\n", name);
end

mode = string(h5read(filename, "/mode"))
sensor_config = jsondecode(string(h5read(filename, "/sensor_config_dump")))
session_info = jsondecode(string(h5read(filename, "/session_info")))

data = h5read(filename, "/data");
disp("Data size =")
disp(size(data))
% Dimensions (frame, sensor, depth) for Envelope, IQ, Power bins
%            (frame, sensor, sweep, depth) for Sparse

if ndims(data) == 3  % Not sparse
    range_start = sensor_config.range_interval(1);
    range_end = sensor_config.range_interval(2);
    depths = linspace(range_start, range_end, size(data, 3));
    frames = 1:size(data, 1);

    data_from_first_sensor = squeeze(data(:, 1, :));
    plot_data = abs(data_from_first_sensor);
    imagesc(frames, depths, plot_data)
    xlabel("Sweeps")
    ylabel("Depth")
end

data_info = jsondecode(string(h5read(filename, "/data_info")));
first_data_info = data_info(1, 1)  % (frame, sensor)

rss_version = string(h5read(filename, "/rss_version"))
lib_version = string(h5read(filename, "/lib_version"))
timestamp = string(h5read(filename, "/timestamp"))
