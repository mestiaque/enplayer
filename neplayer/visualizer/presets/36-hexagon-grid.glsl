// name: Hexagon Grid
// category: Abstract
vec4 hexCell(vec2 p) {
    vec2 s = vec2(1., 1.7320508);
    vec2 h = s * .5;
    vec2 a = mod(p, s) - h, b = mod(p - h, s) - h;
    vec2 g = dot(a, a) < dot(b, b) ? a : b;
    return vec4(g, p - g);
}
vec4 render() {
    vec2 p = P() * 9.;
    vec4 hc = hexCell(p);
    vec2 g = hc.xy, id = hc.zw;
    float edgeDist = .5 - max(abs(g.x), dot(abs(g), normalize(vec2(1., 1.7320508))));
    float r = length(id) / 9.;
    float e = spec(clamp(r * 1.3, 0., 1.));
    float on = smoothstep(.0, .05, edgeDist) * (.15 + e * 1.3 + .4 * uBeat * step(hash(id), .15));
    float edge = line(edgeDist, .03) * .35;
    vec3 col = pal(r + hash(id) * .15 + uTime * .02);
    return vec4(col * on + uC2 * edge * e, on * .9 + edge * e);
}
