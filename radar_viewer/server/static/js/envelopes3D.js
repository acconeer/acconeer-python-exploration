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
var height = 0.005;

lineMaterial = new THREE.LineBasicMaterial({
  color: 0x2888A9, linewidth: 1
});
shapeMaterial = new THREE.MeshBasicMaterial({
  color: 0xF9F9F9, side: THREE.DoubleSide
});

var textMesh = loadThreejsText(['Distance', 'Time', 'Amplitude'], function(textMesh) {
  textMesh[0].rotation.x = -Math.PI / 2;
  textMesh[0].position.z = 5;
  textMesh[0].position.x = -7;
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

getData(function(data) {
  var shape = makeShape(data);
  var curve = makeObjects(shape);
  curves.unshift(curve);
  scene.add(curve);

  if(curves.length > maxCurves) {
    scene.remove(curves.pop());
  }
  curves.forEach(function(curve) {
    curve.position.z -= length / maxCurves;
  });
}, 'envelope');

function makeShape(data) {
  var shape = new THREE.Shape();
  var step = width / (data.length - 1);
  var offset = width / 2;

  shape.moveTo(-offset, 0);
  for(var i = 0; i < data.length; i++) {
    shape.lineTo((step * i) - offset, data[i] * height);
  }
  shape.lineTo(offset, 0);
  shape.lineTo(-offset, 0);
  return shape;
}

function makeObjects(shape) {
  var group = new THREE.Group();

  var geometry = new THREE.ShapeGeometry(shape);
  var mesh = new THREE.Mesh(geometry, shapeMaterial);

  var points = new THREE.Geometry().setFromPoints(shape.getPoints());
  var line = new THREE.Line(points, lineMaterial);

  group.add(line);
  group.add(mesh);
  return group;
}
