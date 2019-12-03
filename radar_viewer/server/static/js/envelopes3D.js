/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var scene, camera, renderer, controls;
initThreejsEnv();

var curves = [];
var maxCurves = 100;
var width = 100;
var length = 150;
var height = 0.02;

lineMaterial = new THREE.LineBasicMaterial({
  color: 0x2888A9, linewidth: 1
});
shapeMaterial = new THREE.MeshBasicMaterial({
  color: 0xF9F9F9, side: THREE.DoubleSide
});

var textMesh = loadThreejsText(['Distance [m]', 'Time', 'Amplitude'], function(textMesh) {
  textMesh[0].rotation.x = -Math.PI / 2;
  textMesh[0].position.z = 5;
  textMesh[0].position.x = -10;
  scene.add(textMesh[0]);
  textMesh[1].rotation.x = -Math.PI / 2;
  textMesh[1].rotation.z = Math.PI / 2;
  textMesh[1].position.x = (width / 2) + 5;
  scene.add(textMesh[1]);
  textMesh[2].rotation.z = Math.PI / 2;
  textMesh[2].rotation.y = Math.PI / 2;
  textMesh[2].position.x = -width / 2;
  textMesh[2].position.z = 3;
  scene.add(textMesh[2]);
});

var grid = new THREE.GridHelper(Math.max(length, width) + 15, 10, 0x808080, 0xD3D3D3);
grid.position.z = -length / 2;
grid.position.y = -10;
scene.add(grid);

controls.target.set(0, 0, -length / 2);
camera.position.y = 80;
camera.position.x = 140;

var prevNbrOfPoints = 0;
getData(function(data) {
  if(data.length != prevNbrOfPoints) {
    prevNbrOfPoints = data.length;
    for(var i = 0; i < curves.length; i++){
      scene.remove(curves[i]);
    }
    curves = [];
  }

  if(curves.length > maxCurves) {
    var last = curves.pop();
    updateObject(data, last);
    last.position.z = 0;
    curves.unshift(last);
  } else {
    var curve = makeObjects(data.length);
    updateObject(data, curve);
    curves.unshift(curve);
    scene.add(curve);
  }

  curves.forEach(function(curve) {
    curve.position.z -= length / maxCurves;
  });
}, 'envelope');

function updateObject(data, shape) {
  for(var i = 0; i < data.length; i++) {
    shape.children[0].geometry.vertices[i + 1].y = data[i] * height;
    shape.children[1].geometry.vertices[i + 1].y = data[i] * height - 0.5;
  }
  shape.children[0].geometry.verticesNeedUpdate = true;
  shape.children[1].geometry.verticesNeedUpdate = true;
}

function makeObjects(datapoints) {
  var group = new THREE.Group();

  var plane = new THREE.PlaneGeometry(width, 0, datapoints, 0);

  var shape = new THREE.Shape();
  var step = width / (datapoints - 1);
  var offset = width / 2;

  shape.moveTo(-offset, 0);
  for(var i = 0; i < datapoints; i++) {
    shape.lineTo((step * i) - offset, 1);
    plane.vertices[i + 1].x = (step * i) - offset;
  }
  shape.lineTo(-offset, 0);

  var mesh = new THREE.Mesh(plane, shapeMaterial);
  mesh.position.y += 0.5;

  var points = new THREE.Geometry().setFromPoints(shape.getPoints());
  var line = new THREE.Line(points, lineMaterial);

  group.add(line);
  group.add(mesh);
  return group;
}
