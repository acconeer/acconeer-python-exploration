/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var config = initChartjsConfig();
config.type = 'line';
config.options.scales.yAxes[0].ticks.max = 16000;
config.options.scales.yAxes[0].ticks.min = 0;
config.options.scales.yAxes[0].scaleLabel.labelString = 'Amplitude';
config.options.scales.xAxes[0].scaleLabel.labelString = 'Distance'

var envelopes = document.getElementById('envelopes').getContext('2d');
var envelopesChart = new Chart(envelopes, config);

getData(function(data) {
  envelopesChart.data.labels = getLabels(data.length, '', false);
  envelopesChart.data.datasets[0].data = data;
  envelopesChart.update();
}, 'envelope');
