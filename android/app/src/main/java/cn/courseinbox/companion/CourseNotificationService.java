package cn.courseinbox.companion;

import android.app.Notification;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/** Receives posted system notifications only after the user grants notification access. */
public final class CourseNotificationService extends NotificationListenerService {
    public static String timestamp(long milliseconds) {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC")); return format.format(new Date(milliseconds));
    }
    @Override public void onListenerConnected() { NotificationQueue.preferences(this).edit().putString("listener_status","通知监听已连接").apply(); NotificationQueue.flush(this); }
    @Override public void onListenerDisconnected() { NotificationQueue.preferences(this).edit().putString("listener_status","通知监听已断开，请检查系统授权").apply(); }
    @Override public void onNotificationPosted(StatusBarNotification posted) {
        if (posted==null || getPackageName().equals(posted.getPackageName())) return;
        String allowed = NotificationQueue.preferences(this).getString("packages","com.chaoxing.mobile");
        boolean accepted=false;
        for (String p:allowed.split("[\\s,;]+")) if (p.equals(posted.getPackageName())) accepted=true;
        if (!accepted) return;
        Notification notification = posted.getNotification();
        if (notification==null || (notification.flags & Notification.FLAG_GROUP_SUMMARY)!=0) return;
        Bundle extras=notification.extras;
        String title=String.valueOf(extras.getCharSequence(Notification.EXTRA_TITLE,""));
        CharSequence big=extras.getCharSequence(Notification.EXTRA_BIG_TEXT);
        String text=String.valueOf(big!=null?big:extras.getCharSequence(Notification.EXTRA_TEXT,""));
        if (text.isEmpty()) {
            CharSequence[] lines=extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
            if (lines!=null) { StringBuilder builder=new StringBuilder(); for(CharSequence line:lines) { if (line!=null) builder.append(line).append('\n'); } text=builder.toString(); }
        }
        if (title.trim().isEmpty() && text.trim().isEmpty()) return;
        try {
            JSONObject event=new JSONObject();
            event.put("package_name",posted.getPackageName()); event.put("notification_key",posted.getKey());
            event.put("title",title);event.put("text",text);event.put("captured_at",timestamp(posted.getPostTime()));
            event.put("scope",NotificationQueue.preferences(this).getString("scope",""));
            event.put("course","");
            if(NotificationQueue.enqueue(this,event)) NotificationQueue.flush(this);
        } catch (Exception error) { NotificationQueue.preferences(this).edit().putString("last_status","通知转换失败，请检查格式。").apply(); }
    }
}
