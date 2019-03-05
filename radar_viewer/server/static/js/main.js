/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

$(document).ready(function() {
  AOS.init({
    once: true
  });
  // For updating range input labels
  $('.custom-range').on('input change', function(event) {
    $('#' + event.target.id + '-label').text($(this).val());
  });
  // Fix for checkbox state for gain and average getting out of sync
  $('[data-toggle="collapse"]').click(function() {
    if($($(this).data('target')).hasClass('collapsing'))
      return false;
  });
  // Add board query to demo pages
  $('.demo-link').click(function() {
    $(this).attr('href', $(this).attr('href') + '?board=' + $('#board').val());
  });
  // Stop data stream when leaving page
  $(window).bind('beforeunload', function() {
    $.getJSON('/stop');
  });
  // Function for terminating server
  $('#exit-button').click(function() {
    $.getJSON('/exit', function() {
      $('body').empty();
      $('body').text('Successfully closed, please close this browser tab.');
    });
  });
  // Remember board selection
  $('#board, #board-welcome').change(function(event) {
    localStorage.setItem('board', event.target.value);
    if(event.target.id == 'board-welcome') {
      $('#board').val(event.target.value).prop('selected', true);
      $('#welcome').modal('hide');
    }
  });
  var board = localStorage.getItem('board');
  var optionExists = !!$('#board option').filter(function(){ return $(this).val() == board; }).length;
  if(optionExists) {
    $('#board').val(board).prop('selected', true);
  } else {
    // If first time show welcome modal with board selection
    //$('#welcome').modal('show');
  }
});

/*
* Get data functions
*/

var demo_name = '';

function getData(callback, name) {
  var dataReceived = false;
  var source = new EventSource('/stream');
  source.onmessage = function(event) {
    if(event.data.indexOf('{') != -1) {
      var msg = JSON.parse(event.data)[demo_name];
      if(msg != null) {
        dataReceived = true;
        callback(msg);
      }
    }
  };
  demo_name = name;

  startDetector(demo_name);
  var timeout = setInterval(function() {
    if(!dataReceived) {
      triggerError(timeoutError);
      clearInterval(timeout);
    }
    dataReceived = false;
  }, 8000);
}

$('#settings-form').submit(function(event) {
  event.preventDefault();
  startDetector(demo_name);
  $('#settings').modal('hide');
});

function startDetector(name) {
  $.getJSON('/stop', function() {
    var data = $('#settings-form').serializeArray();
    // Ignore hidden fields such as gain and average
    if(!$('#gain-check').is(':checked')) {
      data = data.filter(function(item) {
        return item.name !== 'gain';
      });
    }
    if(!$('#average-check').is(':checked')) {
      data = data.filter(function(item) {
        return item.name !== 'average';
      });
    }
    if(!$('#sensitivity-check').is(':checked')) {
      data = data.filter(function(item) {
        return item.name !== 'sensitivity';
      });
    }
    // Get board id from url and append to data
    var boardId = new URL(window.location.href).searchParams.get('board');
    if (boardId == null || boardId == '') {
      triggerError(noBoardSelected);
      return;
    }
    data.push({name: 'board', value: boardId});
    // TEMPORARY solution to range length
    if (name == 'powerbins' || name == 'envelope' || name == 'iq' || name == 'distancepeak') {
        data[1].value = (parseFloat(data[0].value) + parseFloat(data[1].value)).toString();
    }
    $.ajax({
      type: 'GET',
      url: '/start/' + name,
      data: data,
      success: function(result) {
        $('#settings-form').trigger('settingsChanged', [data]);
      }
    });
  });
}

/*
* Chartjs helper functions
*/

function initChartjsConfig() {
  Chart.defaults.global.animation.duration = 100;

  var textColor = 'rgb(33, 37, 41)';
  var lineColor = 'rgb(40, 136, 169)';
  var fillColor = 'rgb(147, 195, 212)';

  var config = {
    data: {
      datasets: [{
        backgroundColor: fillColor,
        borderColor: lineColor,
        borderWidth: 2,
        pointRadius: 0, // Only for line charts
        lineTension: 0, // Only for line charts
        showLine: true,
        fill: false,
        data: []
      }]
    },
    options: {
      tooltips: {
        enabled: false
      },
      legend: {
        display: false
      },
      scales: {
        yAxes: [{
          scaleLabel: {
            display: true,
            fontSize: 20
          },
          ticks: {
            fontSize: 14,
            fontColor: textColor
          },
          gridLines: {
            display: false,
            lineWidth: 2,
            color: lineColor
          }
        }],
        xAxes: [{
          scaleLabel: {
            display: true,
            fontSize: 20
          },
          ticks: {
            fontSize: 14,
            fontColor: textColor,
            autoSkipPadding: 60
          },
          gridLines: {
            display: false,
            lineWidth: 2,
            color: lineColor
          }
        }]
      },
      layout: {
        padding: {
        }
      }
    }
  };
  return config;
}

function initChartDrawLinePlugin() {
  var lineColor = 'rgb(40, 136, 169)';

  const linePlugin = {
    getLinePosition: function(chart, pointIndex) {
      const meta = chart.getDatasetMeta(0); // First dataset is used to discover X coordinate of a point
      const data = meta.data;
      if(data[pointIndex] == null) {
        return null;
      }
      return data[pointIndex]._model.x;
    },
    renderVerticalLine: function(chartInstance, pointIndex) {
      const lineLeftOffset = this.getLinePosition(chartInstance, pointIndex);
      if(lineLeftOffset == null) {
        return;
      }
      this.renderLine(chartInstance, lineLeftOffset, chartInstance.chartArea.top, lineLeftOffset, chartInstance.chartArea.bottom);
    },
    renderHorizontalLine: function(chartInstance, y) {
      var offset = chartInstance.scales['y-axis-1'].getPixelForValue(y);
      this.renderLine(chartInstance, chartInstance.chartArea.left, offset, chartInstance.chartArea.right, offset);
    },
    renderLine: function(chartInstance, x1, y1, x2, y2) {
      const context = chartInstance.chart.ctx;

      // Render line
      context.setLineDash([5, 5]);
      context.beginPath();
      context.strokeStyle = lineColor;
      context.lineWidth = 2;
      context.moveTo(x1, y1);
      context.lineTo(x2, y2);
      context.stroke();
      context.setLineDash([]);
    },
    afterDatasetsDraw: function(chart, easing) {
      if(chart.config.verticallLine) {
        this.renderVerticalLine(chart, chart.config.verticallLine);
      }
      if(chart.config.horizontalLine) {
        this.renderHorizontalLine(chart, chart.config.horizontalLine);
      }
    }
  };
  Chart.plugins.register(linePlugin);
}

function getLabels(length, text, addNumber) {
  var arr = [];
  for(var i = 1; i <= length; i++) {
    if(addNumber) {
      arr.push(text + i);
    } else {
      arr.push(text);
    }
  }
  return arr;
}

/*
* Threejs helper functions
*/

function initThreejsEnv() {
  try {
    renderer = new THREE.WebGLRenderer({'antialias': true});
  } catch(err) { // If browser does not support webgl
    triggerError(webGLError);
  }
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(65, 2, 5, 1000);
  controls = new THREE.OrbitControls(camera, renderer.domElement);

  renderer.setSize(window.innerWidth, window.innerHeight);
  document.body.appendChild(renderer.domElement);
  window.addEventListener('resize', threejsOnWindowResize, false);

  scene.background = new THREE.Color(0x00ffffff);

  controls.screenSpacePanning = false;
  controls.minDistance = 20;
  controls.maxDistance = 200;
  controls.enableDamping = true;
  controls.dampingFactor = 0.1;
  controls.panSpeed = 0.1;
  controls.rotateSpeed = 0.1;
  controls.maxPolarAngle = (Math.PI / 2);
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.15;

  controls.addEventListener('start', function() {
    controls.autoRotate = false;
  });

  function threejsOnWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  }

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  };
  animate();
}

function loadThreejsText(text, callback) {
  textMaterial = new THREE.MeshBasicMaterial({
    color: 0x2888A9
  });
  var textMesh = [];
  var loader = new THREE.FontLoader();
  loader.load('font/helvetiker_regular.typeface.json', function(font) {
    var fontSettings = {
      font: font,
      size: 3,
      height: 0,
      curveSegments: 2
    };
    for(var i = 0; i < text.length; i++) {
      textMesh[i] = new THREE.Mesh(new THREE.TextGeometry(text[i], fontSettings), textMaterial);
    }
    callback(textMesh);
  });
}

/*
* Error handling
*/

function errorModalTemplate(error) {
  return `<div class="modal fade" id="error-message">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">${error.title}</h3>
          <button type="button" class="close" title="Close" data-dismiss="modal">
            <span>&times;</span>
          </button>
        </div>
        <div class="modal-body">
          ${error.body}
        </div>
      </div>
    </div>
  </div>`;
}

var noBoardSelected = {
  title: 'No connector board selected',
  body: '<p>Before starting demo, please go back to the <a href="index.html">main page</a> and select your connector board from the menu.</p>'
}

var timeoutError = {
  title: 'Data stream timeout',
  body: `
    <p class="font-weight-bold">No sensor data has been received, possible causes are:</p>

    <ul>
       <li> XM112 Module with XB112 breakout board:</li>
       <ul>
           <li>The module has not been flashed with a recent module software image</li>
           <li>The computer is not connected to the USB1 port on XB112</li>
       </ul>
       <li> Raspberry Pi with XC111/XC112:</li>
       <ul>
          <li>The streaming server is not running</li>
          <!--  <li>Wrong connector board selected</li> -->
          <li>The sensor is not connected to port one on the connector board</li>
          <li>The Raspberry Pi and the PC are not connected to the same network</li>
          <li>Wrong IP address has been entered when the radar viewer was started</li>
       </ul>
    </ul>
    <p class="font-weight-bold">If none of these causes are listed please try the following:</p>
    <ul>
      <li>Refreshing the page</li>
      <li>Restarting the streaming server, or disconnect and reconnect the module</li>
    </ul>
  `
}

var webGLError = {
  title: 'Error while initializing renderer',
  body: '<p>Does your browser support <a href="https://get.webgl.org/">WebGL</a>?</p>'
}

function triggerError(errorMessage) {
  $('body').append(errorModalTemplate(errorMessage));
  $('#error-message').modal('show');
}
