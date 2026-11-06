// name: Dot Wave Field
// category: Particles
vec4 render() {
    vec2 uv = UV();
    vec2 g = vec2(64., 36.);
    vec2 cell = floor(uv * g), f = fract(uv * g) - .5;
    vec2 cc = (cell + .5) / g;
    float dc = length((cc - .5) * vec2(uRes.x / uRes.y, 1.));
    float e = spec(clamp(dc * 1.3, 0., 1.));
    float wave_ = sin(dc * 18. - uTime * 3. * uMotion) * .5 + .5;
    float lift = wave_ * (.25 + e);
    float size = .08 + lift * .35;
    float d = length(f);
    float s = smoothstep(size, size * .6, d);
    vec3 col = pal(dc + lift * .4 + uTime * .02);
    return vec4(col * s * (.35 + lift * 1.8), s * (.45 + lift));
}
