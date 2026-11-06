// name: Cyberpunk HUD Equalizer
// category: Sci-fi
vec4 render() {
    vec2 uv = UV();
    float glitch = step(.92, hash(vec2(floor(uTime * 12.), floor(uv.y * 30.)))) * uBeat * uMotion;
    uv.x += glitch * .02;
    float n = 40.;
    float cell = fract(uv.x * n);
    float x = (floor(uv.x * n) + .5) / n;
    float v = spec(x) * .8;
    float y = uv.y - .1;
    float seg = step(.35, fract(y * 60.));
    float bar = step(0., y) * step(y, v) * step(.2, cell) * step(cell, .8) * seg;
    float scan = .85 + .15 * sin(gl_FragCoord.y * 1.5);
    vec3 col = mix(uC1, uC3, smoothstep(0., .7, y));
    float frame = (line(uv.y - .08, .0015) + line(uv.y - .93, .0015)) * .6;
    float tick = step(.97, fract(uv.x * 20.)) * step(abs(uv.y - .08), .015);
    float rgb = bar * scan;
    return vec4(col * rgb + vec3(1, .2, .5) * glitch * .3 + uC2 * (frame + tick), rgb + frame + tick + glitch * .3);
}
