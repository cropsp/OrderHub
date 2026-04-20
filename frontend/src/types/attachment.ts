export type AttachmentType = 'mockup' | 'reference' | 'other';

export interface AttachmentResponse {
  id: string;
  order_id: string;
  uploaded_by_id: string;
  file_name: string;
  original_name?: string;
  file_size: number;
  mime_type: string;
  attachment_type: AttachmentType;
  created_at: string;
}
