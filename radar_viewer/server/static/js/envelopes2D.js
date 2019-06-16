/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var config = initChartjsConfig();
config.type = 'line';
config.options.scales.yAxes[0].ticks.max = 10000;
config.options.scales.yAxes[0].ticks.min = 0;
config.options.scales.yAxes[0].scaleLabel.labelString = 'Amplitude';
config.options.scales.xAxes[0].scaleLabel.labelString = 'Distance [m]'

var envelopes = document.getElementById('envelopes').getContext('2d');
var envelopesChart = new Chart(envelopes, config);

getData(function(data) {
  envelopesChart.data.labels = getDistLabels(data.length);
  envelopesChart.data.datasets[0].data = data;
  envelopesChart.update();
}, 'envelope');

var start = 0;
var end = 0;

$('#settings-form').on('settingsChanged', function(event, data) {
  start = +(data.filter(function(item) {
    return item.name == 'range_start';
  })[0]['value']);
  end = +(data.filter(function(item) {
    return item.name == 'range_end';
  })[0]['value']);
  config.options.scales.yAxes[0].ticks.max = +(data.filter(function(item) {
    return item.name == 'plot_range';
  })[0]['value']);
});

function getDistLabels(length) {
  var arr = [];
  var step = (end - start) / length;
  for(var i = 0; i < length; i++) {
    var dist = start + step * i;
    arr.push(dist.toFixed(2));
  }
  return arr;
}
