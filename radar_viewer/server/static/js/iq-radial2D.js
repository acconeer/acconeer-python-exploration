/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var lineColor = 'rgb(40, 136, 169)';
var axisColor = 'rgb(53, 74, 83)';
var lineWidth = 4;
var pointRadius = 5;
var tailDuration = 0.5;
var tailWidth = 1.5;
var phaseAmplitude = 5;

initChartDrawLinePlugin();

var amplitudeConfig = initChartjsConfig();
amplitudeConfig.type = 'line';
amplitudeConfig.options.maintainAspectRatio = true;
amplitudeConfig.options.scales.yAxes[0].ticks.max = 0.5;
amplitudeConfig.options.scales.yAxes[0].ticks.min = 0;
amplitudeConfig.options.scales.yAxes[0].gridLines.drawTicks = false;
amplitudeConfig.options.scales.yAxes[0].ticks.display = false;
amplitudeConfig.options.scales.yAxes[0].scaleLabel.display = false;
amplitudeConfig.options.scales.xAxes[0].gridLines.drawTicks = false;
amplitudeConfig.options.scales.xAxes[0].ticks.display = false;
amplitudeConfig.options.scales.xAxes[0].scaleLabel.display = false;
amplitudeConfig.options.layout.padding.left = 8;
amplitudeConfig.options.layout.padding.right = 8;
amplitudeConfig.options.layout.padding.bottom = 13;


var phaseConfig = initChartjsConfig();
phaseConfig.type = 'scatter';
phaseConfig.options.maintainAspectRatio = true;
phaseConfig.options.aspectRatio = 1;
phaseConfig.data.datasets[0].borderWidth = 4;
phaseConfig.data.datasets[0].pointRadius = pointRadius;
phaseConfig.options.scales.yAxes[0].ticks.max = 1;
phaseConfig.options.scales.yAxes[0].ticks.min = -1;
phaseConfig.options.scales.yAxes[0].gridLines.display = true;
phaseConfig.options.scales.yAxes[0].gridLines.color = 'transparent';
phaseConfig.options.scales.yAxes[0].gridLines.zeroLineColor = axisColor;
phaseConfig.options.scales.yAxes[0].gridLines.zeroLineWidth = 2;
phaseConfig.options.scales.yAxes[0].gridLines.drawTicks = false;
phaseConfig.options.scales.yAxes[0].ticks.display = false;
phaseConfig.options.scales.yAxes[0].scaleLabel.display = false;
phaseConfig.options.scales.xAxes[0].ticks.max = 1;
phaseConfig.options.scales.xAxes[0].ticks.min = -1;
phaseConfig.options.scales.xAxes[0].gridLines.display = true;
phaseConfig.options.scales.xAxes[0].gridLines.color = 'transparent';
phaseConfig.options.scales.xAxes[0].gridLines.zeroLineColor = axisColor;
phaseConfig.options.scales.xAxes[0].gridLines.zeroLineWidth = 2;
phaseConfig.options.scales.xAxes[0].gridLines.drawTicks = false;
phaseConfig.options.scales.xAxes[0].ticks.display = false;
phaseConfig.options.scales.xAxes[0].scaleLabel.display = false;

// Add dataset for the tail
phaseConfig.data.datasets.push({
  borderColor: lineColor,
  borderWidth: tailWidth,
  pointRadius: 0,
  showLine: true,
  fill: false,
  data: []
});

var iqAmplitude = document.getElementById('iq-amplitude').getContext('2d');
var iqAmplitudeChart = new Chart(iqAmplitude, amplitudeConfig);

var iqPhase = document.getElementById('iq-phase').getContext('2d');
var iqPhaseChart = new Chart(iqPhase, phaseConfig);

var tailLength = 0;
var tail = [];
var index = 0;
var nbrOfPoints = 1;
var start = 0;
var end = 0;

var firstTime = true;

$('#settings-form').on('settingsChanged', function(event, data) {
  start = +(data.filter(function(item) {
    return item.name == 'range_start';
  })[0]['value']);
  end = +(data.filter(function(item) {
    return item.name == 'range_end';
  })[0]['value']);

  var freq = +(data.filter(function(item) {
    return item.name == 'frequency';
  })[0]['value']);
  tailLength = freq * tailDuration;

  $('#dist').trigger('change');
});

$('#dist').on('input change', function(event) {
  index = $(this).val();

  iqAmplitudeChart.config.verticallLine = index;
  iqAmplitudeChart.update();

  var distance = Math.round((start + ((index / nbrOfPoints) * (end - start))) * 100) / 100;

  $('#dist-label-custom').text(distance);
  $('#dist-at-label').text(distance);
  tail = [];
});

getData(function(data) {
  nbrOfPoints = data.length;
  $('#dist').attr('max', nbrOfPoints - 1);

  // Double check that index is within range
  if(index >= data.length) {
    $('#dist').trigger('change');
    return;
  }

  if(firstTime){
    firstTime = false;
    $('#dist').val(22);
    $('#dist').trigger('change');
  }

  var amplitude = [];
  for(var i = 0; i < data.length; i++) {
    amplitude[i] = Math.sqrt(data[i]['re'] * data[i]['re'] + data[i]['im'] * data[i]['im']);
  }

  phase = Math.atan2(data[index]['re'], data[index]['im']);
  // Scale the amplitude to be between 0 and 1
  scaledAmp = Math.tanh(amplitude[index] * phaseAmplitude);

  re = scaledAmp * Math.cos(phase);
  im = scaledAmp * Math.sin(phase);

  tail.push({
    x: re,
    y: im
  });
  if(tail.length > tailLength) {
    tail.shift();
  }

  var phase = [{
      x: 0,
      y: 0
    }, {
      x: re,
      y: im
    }];

  iqAmplitudeChart.data.labels = getLabels(data.length, '', false);
  iqAmplitudeChart.data.datasets[0].data = amplitude;
  iqAmplitudeChart.update();

  iqPhaseChart.data.labels = getLabels(data.length, '', false);
  iqPhaseChart.data.datasets[0].data = phase;
  iqPhaseChart.data.datasets[1].data = tail;
  iqPhaseChart.update();
}, 'iq');
