/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var lineColor = 'rgb(40, 136, 169)';
var lineWidth = 4;
var pointRadius = 5;
var tailDuration = 0.5;
var tailWidth = 1.5;

initChartDrawLinePlugin();

var amplitudeConfig = initChartjsConfig();
amplitudeConfig.type = 'line';
amplitudeConfig.options.maintainAspectRatio = true;
amplitudeConfig.options.scales.yAxes[0].ticks.max = 1;
amplitudeConfig.options.scales.yAxes[0].ticks.min = 0;
amplitudeConfig.options.scales.yAxes[0].gridLines.drawTicks = false;
amplitudeConfig.options.scales.yAxes[0].ticks.display = false;
amplitudeConfig.options.scales.yAxes[0].scaleLabel.display = false;
amplitudeConfig.options.scales.xAxes[0].gridLines.drawTicks = false;
amplitudeConfig.options.scales.xAxes[0].ticks.display = false;
amplitudeConfig.options.scales.xAxes[0].scaleLabel.display = false;
amplitudeConfig.options.layout.padding.left = 8;
amplitudeConfig.options.layout.padding.right = 8;
amplitudeConfig.options.layout.padding.bottom = 12;


var phaseConfig = initChartjsConfig();
phaseConfig.type = 'scatter';
phaseConfig.options.maintainAspectRatio = true;
phaseConfig.options.aspectRatio = 1;
phaseConfig.data.datasets[0].borderWidth = lineWidth;
phaseConfig.data.datasets[0].pointRadius = pointRadius;
phaseConfig.options.scales.yAxes[0].ticks.max = 1;
phaseConfig.options.scales.yAxes[0].ticks.min = -1;
phaseConfig.options.scales.yAxes[0].gridLines.display = true;
phaseConfig.options.scales.yAxes[0].gridLines.color = 'transparent';
phaseConfig.options.scales.yAxes[0].gridLines.zeroLineColor = lineColor;
phaseConfig.options.scales.yAxes[0].gridLines.zeroLineWidth = 2;
phaseConfig.options.scales.yAxes[0].gridLines.drawTicks = false;
phaseConfig.options.scales.yAxes[0].ticks.display = false;
phaseConfig.options.scales.yAxes[0].scaleLabel.display = false;
phaseConfig.options.scales.xAxes[0].ticks.max = 1;
phaseConfig.options.scales.xAxes[0].ticks.min = -1;
phaseConfig.options.scales.xAxes[0].gridLines.display = true;
phaseConfig.options.scales.xAxes[0].gridLines.color = 'transparent';
phaseConfig.options.scales.xAxes[0].gridLines.zeroLineColor = lineColor;
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

  var current = $('#dist').attr('value');
  if(current < start) {
    $('#dist').attr('value', start);
  } else if (current > end) {
    $('#dist').attr('value', end);
  }

  $('#dist').trigger('change');
});

$('#dist').on('input change', function(event) {
  index = $(this).val();

  iqAmplitudeChart.config.verticallLine = index;
  iqAmplitudeChart.update();

  $('#dist-label-custom').text(Math.round((start + ((index / nbrOfPoints) * (end - start))) * 100) / 100);
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

  tail.push({
    x: data[index]['re'],
    y: data[index]['im']
  });
  if(tail.length > tailLength) {
    tail.shift();
  }

  var phase = [{
      x: 0,
      y: 0
    }, {
      x: data[index]['re'],
      y: data[index]['im']
    }];

  var amplitude = [];
  for(var i = 0; i < data.length; i++) {
    amplitude[i] = Math.sqrt(data[i]['re'] * data[i]['re'] + data[i]['im'] * data[i]['im']);
  }
  iqAmplitudeChart.data.labels = getLabels(data.length, '', false);
  iqAmplitudeChart.data.datasets[0].data = amplitude;
  iqAmplitudeChart.update();

  iqPhaseChart.data.labels = getLabels(data.length, '', false);
  iqPhaseChart.data.datasets[0].data = phase;
  iqPhaseChart.data.datasets[1].data = tail;
  iqPhaseChart.update();
}, 'iq');
