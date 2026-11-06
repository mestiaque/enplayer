// name: Spectrogram Waterfall
// category: Bars
vec4 render() {
    vec2 uv = UV();
    float age = 1. - uv.x;                     // newest at the right edge
    float v = hist(uv.y, age);
    vec3 col = v < .33 ? mix(vec3(0.), uC1, v * 3.) : v < .66 ? mix(uC1, uC2, (v - .33) * 3.) : mix(uC2, vec3(1.), (v - .66) * 3.);
    float edge = line(uv.x - 1. + 1. / 64., .002) * .5;
    return vec4(col + vec3(edge), clamp(v * 1.5, 0., 1.) + edge);
}
