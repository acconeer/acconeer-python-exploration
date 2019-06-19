/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var pointRadius = 5;
var dataPointDist = 0.06;

var config = initChartjsConfig();
config.type = 'scatter';
config.data.datasets[0].borderWidth = 4;
config.data.datasets[0].pointRadius = pointRadius;
config.data.datasets[0].showLine = false;
config.options.scales.yAxes[0].ticks.max = 30000;
config.options.scales.yAxes[0].ticks.min = -30000;
config.options.scales.yAxes[0].scaleLabel.labelString = 'Amplitude';
config.options.scales.xAxes[0].scaleLabel.labelString = 'Distance [m]';
config.options.scales.xAxes[0].ticks.stepSize = 0.01;
config.options.scales.xAxes[0].ticks.autoSkip = false;
config.options.scales.xAxes[0].ticks.callback = function(value, index, values) {
  if(Math.round(value * 100) % Math.round(dataPointDist * 100) != 0) {
    return null;
  }
  return Math.round(value * 100) / 100;
}

var sparse = document.getElementById('sparse').getContext('2d');
var sparseChart = new Chart(sparse, config);

getData(function(data) {
  var points = []

  for(var i = 0; i < data.length; i++) {
    var sweep = data[i];
    for(var j = 0; j < sweep.length; j++) {
      var xpos = j * dataPointDist + actualStart;
      if(Math.abs(xpos - start) < 0.01 || Math.abs(xpos - end) < 0.01) {
        continue;
      }
      points.push({
        x: xpos,
        y: sweep[j]
      });
    }
  }
  sparseChart.data.datasets[0].data = points;
  sparseChart.update();
}, 'sparse');

var start = 0;
var end = 0;
var actualStart = 0;

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
  config.options.scales.yAxes[0].ticks.min = -(data.filter(function(item) {
    return item.name == 'plot_range';
  })[0]['value']);
  actualStart = Math.round(start / dataPointDist) * dataPointDist;
  config.options.scales.xAxes[0].ticks.max = end;
  config.options.scales.xAxes[0].ticks.min = start;
});
