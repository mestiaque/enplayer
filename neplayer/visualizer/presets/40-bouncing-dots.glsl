// name: Bouncing Dots
// category: Bars
vec4 render() {
    vec2 uv = UV();
    vec2 p = vec2(uv.x * uRes.x / uRes.y, uv.y);
    float n = 24.;
    float cx = floor(uv.x * n);
    float x = (cx + .5) / n;
    float h = .12 + spec(x) * .7;
    vec2 c = vec2(x * uRes.x / uRes.y, h);
    float rad = .018 + spec(x) * .025;
    float d = length(p - c);
    float ball = smoothstep(rad, rad - .003, d);
    float g = glow(d - rad, .01) * .6;
    float stem = step(abs(p.x - c.x), .002) * step(.08, uv.y) * step(uv.y, h - rad) * .25;
    float shadow = smoothstep(.02, 0., abs(uv.y - .08)) * smoothstep(rad * 2., 0., abs(p.x - c.x)) * .4;
    vec3 col = pal(x + uTime * .03);
    return vec4(col * (ball + g + stem + shadow), ball + g + stem + shadow);
}
