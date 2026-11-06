// name: Classic Vertical EQ Bars
// category: Bars
vec4 render() {
    vec2 uv = UV();
    float n = floor(mix(32., 96., clamp(uDensity, 0., 1.)));
    float cell = fract(uv.x * n);
    float x = (floor(uv.x * n) + .5) / n;
    float y = (uv.y - .04) / .88;
    float v = spec(x), pk = peak(x);
    float gap = step(.14, cell) * step(cell, .86);
    float bar = step(0., y) * step(y, v) * gap;
    vec3 col = pal3(y);
    float cap = gap * step(0., y) * line(y - pk - .012, .006);
    float refl = step(y, 0.) * step(-y, v * .35) * gap * (1. + y * 3.) * .25;
    return vec4(col * bar + vec3(1.) * cap + col * max(refl, 0.), max(max(bar, cap), max(refl, 0.)));
}
