// name: Synthwave Grid
// category: Retro
vec4 render() {
    vec2 uv = UV();
    vec3 c = vec3(0); float a = 0.;
    float horizon = .42;
    float aspect = uRes.x / uRes.y;
    // sun with scrolling cut-outs
    vec2 sp = vec2((uv.x - .5) * aspect, uv.y - horizon - .14);
    float R = .2 + .02 * uBass * uMotion;
    float sun = smoothstep(R + px(), R, length(sp)) * step(horizon, uv.y);
    float sy = (sp.y + R) / (2. * R);
    float cut = step(.5 - .45 * (1. - sy), fract(sy * 9. - uTime * .3 * uMotion));
    sun *= mix(cut, 1., step(.55, sy));
    c += mix(uC3, uC2, sy) * sun * (1. + .4 * uBass);
    a += sun;
    c += uC3 * exp(-max(length(sp) - R, 0.) * 9.) * .35 * step(horizon, uv.y);
    // mountains: spectrum silhouette on the horizon
    float m = spec(abs(uv.x - .5) * 2.) * .16 * (.5 + abs(uv.x - .5));
    float mount = step(horizon, uv.y) * step(uv.y, horizon + m);
    c = mix(c, uC1 * .18, mount);
    float mEdge = line(uv.y - horizon - m, 1.5 * px()) * step(horizon, uv.y);
    c += uC1 * mEdge; a = max(a, max(mount * .95, mEdge));
    // perspective floor grid
    if (uv.y < horizon) {
        float d = horizon - uv.y;
        float z = .6 / d;                                  // depth
        float xw = (uv.x - .5) * aspect * z;
        float zz = z + uTime * 1.2 * uMotion;
        vec2 fw = vec2(fwidth(xw), fwidth(zz));
        vec2 gl2 = abs(fract(vec2(xw * 3., zz)) - .5) / max(fw * vec2(3., 1.), 1e-4);
        float grid = 1. - smoothstep(0., 1.5, min(gl2.x, gl2.y));
        float fade = smoothstep(0., .12, d);
        float e = .9 + 1.4 * spec(clamp(abs(uv.x - .5) * 2., 0., 1.)) + uBeat * .4;
        c += uC1 * grid * fade * e;
        a += grid * fade;
        c += uC2 * .12 * exp(-d * 20.); a += .12 * exp(-d * 20.);
    }
    c += uC2 * line(uv.y - horizon, 1.2 * px()) * 1.2;
    return vec4(c, clamp(a, 0., 1.));
}
