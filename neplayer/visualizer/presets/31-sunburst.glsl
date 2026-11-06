// name: Spectrum Sunburst
// category: Circular
vec4 render() {
    vec2 p = P();
    float r = length(p), a = atan(p.x, p.y);
    float t = abs(a) / PI;
    float rays = 60.;
    float id = (floor(t * rays) + .5) / rays;
    float v = spec(id);
    float cell = fract(t * rays);
    float wedge = smoothstep(.0, .3, cell) * smoothstep(1., .7, cell);
    float len = .08 + v * .55;
    float ray = wedge * smoothstep(len, len - .02, r) * smoothstep(.04, .07, r);
    float fade = 1. - r / max(len, .01);
    vec3 col = pal3(r * 1.6);
    float core = exp(-r * 18.) * (.6 + uBass);
    return vec4(col * ray * (.35 + fade) + uC2 * core, ray * (.4 + fade * .6) + core);
}
