The documentation is available over at <https://docs.acconeer.com>.

Shrink images before committing them, since git keeps every byte:
`hatch run docs:compress-images <paths>`. Store photos as JPEG (`--to-jpeg`
converts a PNG), and screenshots and diagrams as PNG.
