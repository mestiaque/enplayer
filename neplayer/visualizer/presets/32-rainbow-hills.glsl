// name: Rainbow Spectrum Hills
// category: Bars
vec4 render() {
    vec2 uv = UV();
    vec3 c = vec3(0); float a = 0.;
    for (int i = 0; i < 6; i++) {
        float fi = float(i);
        float off = fi * .03;
        float h = spec(clamp(uv.x + off - .05, 0., 1.)) * (.55 - fi * .06) + .05;
        float hill = smoothstep(h + .003, h, uv.y);
        float top = line(uv.y - h, .002);
        vec3 col = .5 + .5 * cos(TAU * (fi / 6. + uv.x * .6 + vec3(0., .33, .67)));
        c = mix(c, col * (.35 + .65 * uv.y / max(h, .01)), hill * .85);
        c += col * top;
        a = max(a, hill * .85 + top);
    }
    return vec4(c, a);
}
