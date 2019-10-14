#!/bin/bash

datetime=$( gawk 'BEGIN {FS="|"}  $1 ~ /Datum und Uhrzeit  / {print $2}' exif.txt )
echo $datetime
focal=$( gawk 'BEGIN {FS="|"}  $1 ~ /Brennweite/ {print $2}' exif.txt )
echo $focal
exposure=$( gawk 'BEGIN {FS="|"}  $1 ~ /Belichtungszeit/ {print $2}' exif.txt )
echo $exposure
aperture=$( gawk 'BEGIN {FS="|"}  $1 ~ /Blendenwert/ {print $2}' exif.txt )
echo $aperture
iso=$( gawk 'BEGIN {FS="|"}  $1 ~ /ISO-Empfindlichkeits/ {print $2}' exif.txt )
echo $iso
speed=$(<speed.txt)
echo $speed

convert capt0000.jpg -strokewidth 0 -fill "rgba( 0, 0, 0, 1 )" -draw "rectangle 0,0 6000,300 " -font helvetica -fill white -pointsize 100 -draw "text 30,130 'SPEED'" -fill white -pointsize 100 -draw "text 30,230 '$speed'" -fill white -pointsize 100 -draw "text 500,130 'DIR'" -fill white -pointsize 100 -draw "text 500,230 'V'" -fill white -pointsize 100 -draw "text 700,130 'DATE'" -fill white -pointsize 100 -draw "text 700,230 '$datetime'" -fill white -pointsize 100 -draw "text 1200,130 ' H:M:S'" -fill white -pointsize 100 -draw "text 1700,130 'CODE'" -fill white -pointsize 100 -draw "text 1700,230 'SPEEDCAT'" -fill white -pointsize 100 -draw "text 2300,130 'FOTO'" -fill white -pointsize 100 -draw "text 2300,230 '0001'" -fill white -pointsize 100 -draw "text 2700,130 'MAX'" -fill white -pointsize 100 -draw "text 2700,230 '20km/h'" -fill white -pointsize 100 -draw "text 3200,130 'EXPOSURE'" -fill white -pointsize 100 -draw "text 3200,230 '$exposure'" -fill white -pointsize 100 -draw "text 4100,130 'ISO'" -fill white -pointsize 100 -draw "text 4100,230 '$iso'" -fill white -pointsize 100 -draw "text 4500,130 'APERTURE'" -fill white -pointsize 100 -draw "text 4500,230 '$aperture'" -fill white -pointsize 100 -draw "text 5200,130 'FOCAL'" -fill white -pointsize 100 -draw "text 5200,230 '$focal'" SpeedCatImage.jpg