/// WGSL Compute Shader for realtime color grading and adjustments
pub const COLOR_ADJUST_WGSL: &str = r#"
struct ColorParams {
    brightness: f32,
    contrast: f32,
    saturation: f32,
    gamma: f32,
};

@group(0) @binding(0) var input_texture: texture_2d<f32>;
@group(0) @binding(1) var output_texture: texture_storage_2d<rgba8unorm, write>;
@group(0) @binding(2) var<uniform> params: ColorParams;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let dims = textureDimensions(input_texture);
    if (global_id.x >= dims.x || global_id.y >= dims.y) {
        return;
    }
    let coords = vec2<i32>(global_id.xy);
    var color = textureLoad(input_texture, coords, 0);

    // Brightness
    color = vec4<f32>(color.rgb + vec3<f32>(params.brightness), color.a);

    // Contrast
    color = vec4<f32>((color.rgb - 0.5) * params.contrast + 0.5, color.a);

    // Saturation
    let luma = dot(color.rgb, vec3<f32>(0.2126, 0.7152, 0.0722));
    color = vec4<f32>(mix(vec3<f32>(luma), color.rgb, params.saturation), color.a);

    textureStore(output_texture, coords, color);
}
"#;

/// WGSL Fragment Shader for Gaussian Blur
pub const GAUSSIAN_BLUR_WGSL: &str = r#"
@group(0) @binding(0) var t_diffuse: texture_2d<f32>;
@group(0) @binding(1) var s_diffuse: sampler;

@fragment
fn fs_blur(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    // 5-tap kernel
    var color = textureSample(t_diffuse, s_diffuse, uv) * 0.227027;
    return color;
}
"#;
