/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var config = initChartjsConfig();
config.type = 'bar';
config.options.scales.yAxes[0].ticks.max = 500;
config.options.scales.yAxes[0].ticks.min = 0;
config.options.scales.yAxes[0].scaleLabel.labelString = 'Amplitude';
config.options.scales.xAxes[0].scaleLabel.labelString = 'Distance'

var powerbin = document.getElementById('powerbin').getContext('2d');
var powerbinChart = new Chart(powerbin, config);

getData(function(data) {
  powerbinChart.data.labels = getLabels(data.length, 'Bin ', true);
  powerbinChart.data.datasets[0].data = data;
  powerbinChart.update();
}, 'powerbins');
