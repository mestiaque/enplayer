// name: Neon Spectrum
// category: Bars
vec4 render() {
    vec2 uv = UV();
    float y = .14 + spec(uv.x) * .62;
    float y2 = .14 + spec(uv.x + 1. / uRes.x) * .62;
    float slope = (y2 - y) * uRes.y;
    float d = (uv.y - y) * uRes.y / sqrt(1. + slope * slope);
    float lineCore = smoothstep(2.5, 0., abs(d));
    float g = exp(-abs(d) / (14. * uGlow));
    float fill = step(uv.y, y) * step(.14, uv.y) * mix(.05, .35, (uv.y - .14) / max(y - .14, .01));
    // synthwave floor grid below the horizon
    float floorY = .14 - uv.y;
    float gridA = 0.;
    if (floorY > 0.) {
        float z = 1. / (floorY * 8. + .05);
        float gx = abs(fract((uv.x - .5) * z * 1.6) - .5);
        float gz = abs(fract(z * .6 - uTime * .6 * uMotion) - .5);
        gridA = (smoothstep(.47, .5, max(gx, gz))) * smoothstep(0., .14, floorY) * .6;
    }
    vec3 col = pal(uv.x + uTime * .03);
    return vec4(col * (lineCore + g * .8 + fill) + uC2 * gridA, lineCore + g * .8 + fill + gridA);
}
