/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var amplitudeConfig = initChartjsConfig();
amplitudeConfig.type = 'line';
amplitudeConfig.options.maintainAspectRatio = false;
amplitudeConfig.options.scales.yAxes[0].ticks.max = 1;
amplitudeConfig.options.scales.yAxes[0].ticks.min = 0;
amplitudeConfig.options.scales.yAxes[0].ticks.stepSize = 0.2;
amplitudeConfig.options.scales.xAxes[0].scaleLabel.labelString = 'Distance'

var phaseConfig = initChartjsConfig();
phaseConfig.type = 'line';
phaseConfig.data.datasets[0].fill = 'false';
phaseConfig.options.maintainAspectRatio = false;
phaseConfig.options.scales.yAxes[0].ticks.max = 1;
phaseConfig.options.scales.yAxes[0].ticks.min = -1;
phaseConfig.options.scales.yAxes[0].ticks.stepSize = 0.5;
phaseConfig.options.scales.yAxes[0].ticks.callback = function(value, index, values) {return value + 'π';}
phaseConfig.options.scales.xAxes[0].scaleLabel.labelString = 'Distance'

var iqAmplitude = document.getElementById('iq-amplitude').getContext('2d');
var iqAmplitudeChart = new Chart(iqAmplitude, amplitudeConfig);

var iqPhase = document.getElementById('iq-phase').getContext('2d');
var iqPhaseChart = new Chart(iqPhase, phaseConfig);

getData(function(data) {
  var amplitude = [];
  var phase = [];
  for (var i = 0; i < data.length; i++) {
    amplitude[i] = Math.sqrt(data[i]['re'] * data[i]['re'] + data[i]['im'] * data[i]['im']);
    // Rescale phase to -1, 1 instead of -pi, pi to fit graph
    phase[i] = Math.atan(data[i]['im'] / data[i]['re']) / (Math.PI / 2);
  }
  iqAmplitudeChart.data.labels = getLabels(data.length, '', false);
  iqAmplitudeChart.data.datasets[0].data = amplitude;
  iqAmplitudeChart.update();

  iqPhaseChart.data.labels = getLabels(data.length, '', false);
  iqPhaseChart.data.datasets[0].data = phase;
  iqPhaseChart.update();
}, 'iq');
