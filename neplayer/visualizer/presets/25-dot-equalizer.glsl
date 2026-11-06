// name: Dot Matrix Equalizer
// category: Bars
vec4 render() {
    vec2 uv = UV();
    vec2 g = vec2(48., 26.);
    vec2 cell = floor(uv * g), f = fract(uv * g) - .5;
    float x = (cell.x + .5) / g.x, y = (cell.y + .5) / g.y;
    float v = spec(x);
    float on = step(y, v * .95);
    float pk = step(abs(cell.y - floor(peak(x) * .95 * g.y)), .5);
    float dotm = smoothstep(.32, .26, length(f));
    vec3 col = pal3(y);
    float b = max(on, pk * .9);
    return vec4(col * dotm * mix(.08, 1., b), dotm * mix(.25, 1., b));
}
