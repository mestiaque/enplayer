// name: Ripple Pond
// category: Abstract
vec4 render() {
    vec2 p = P();
    float h = 0.;
    for (int i = 0; i < 4; i++) {
        float fi = float(i);
        vec2 src = (hash2(vec2(fi, 2.)) - .5) * vec2(.9, .5);
        float d = length(p - src);
        float ph = uTime * (.8 + fi * .1) * uMotion;
        float e = spec(.05 + fi * .2);
        h += sin(d * 60. - ph * 6.) * exp(-d * 4.) * (.3 + e * 1.6);
    }
    vec2 grad = vec2(dFdx(h), dFdy(h)) * 40.;
    float light = clamp(.5 + dot(normalize(vec3(-grad, 1.)), normalize(vec3(.4, .5, .8))) * .5, 0., 1.);
    float caustic = pow(light, 6.) * 1.5;
    vec3 water = mix(uC1 * .25, uC2 * .7, light) + uC3 * caustic * (.5 + uBass);
    return vec4(water, 1.);
}
