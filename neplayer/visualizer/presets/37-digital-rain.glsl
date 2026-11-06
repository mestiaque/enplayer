// name: Digital Rain
// category: Sci-fi
vec4 render() {
    vec2 uv = UV();
    float cols = 64.;
    float cx = floor(uv.x * cols);
    float x = (cx + .5) / cols;
    float e = spec(abs(x - .5) * 2.);
    float speed = (.3 + hash(vec2(cx, 3.)) * .6) * (1. + 2. * uLevel) * uMotion;
    float y = uv.y + uTime * speed + hash(vec2(cx, 1.)) * 10.;
    vec2 g = vec2(uv.x * cols, y * 30.);
    vec2 cell = floor(g), f = fract(g);
    float glyph = step(.5, hash(cell + floor(uTime * 8.))) * step(.15, f.x) * step(f.x, .85) * step(.15, f.y) * step(f.y, .85);
    float trail = fract(-y * 1.2);
    trail = pow(trail, 3.) * (.3 + 1.5 * e);
    float head = smoothstep(.97, 1., fract(-y * 1.2));
    vec3 col = mix(uC1, vec3(1.), head);
    return vec4(col * glyph * (trail + head), glyph * (trail + head));
}
