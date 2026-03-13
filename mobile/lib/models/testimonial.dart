import 'package:json_annotation/json_annotation.dart';

part 'testimonial.g.dart';

@JsonSerializable()
class Testimonial {
  final int id;
  final String authorName;
  final String? authorEmail;
  final String? authorAvatar;
  final String content;
  final int rating;
  final bool isActive;
  final DateTime createdAt;
  final List<TestimonialMedia>? media;

  Testimonial({
    required this.id,
    required this.authorName,
    this.authorEmail,
    this.authorAvatar,
    required this.content,
    required this.rating,
    required this.isActive,
    required this.createdAt,
    this.media,
  });

  factory Testimonial.fromJson(Map<String, dynamic> json) => _$TestimonialFromJson(json);
  Map<String, dynamic> toJson() => _$TestimonialToJson(this);
}

@JsonSerializable()
class TestimonialMedia {
  final int id;
  final String file;
  final String? caption;
  final DateTime createdAt;

  TestimonialMedia({
    required this.id,
    required this.file,
    this.caption,
    required this.createdAt,
  });

  factory TestimonialMedia.fromJson(Map<String, dynamic> json) => _$TestimonialMediaFromJson(json);
  Map<String, dynamic> toJson() => _$TestimonialMediaToJson(this);
}

@JsonSerializable()
class TestimonialCreate {
  final String content;
  final int rating;
  final List<String>? mediaFiles;

  TestimonialCreate({
    required this.content,
    required this.rating,
    this.mediaFiles,
  });

  factory TestimonialCreate.fromJson(Map<String, dynamic> json) => _$TestimonialCreateFromJson(json);
  Map<String, dynamic> toJson() => _$TestimonialCreateToJson(this);
}
