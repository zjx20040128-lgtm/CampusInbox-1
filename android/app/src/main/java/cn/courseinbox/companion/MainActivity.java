package cn.courseinbox.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.provider.Settings;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.net.URI;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private EditText server,token,scope,packages;
    private TextView status;
    private final Handler handler=new Handler();
    private final Runnable update=new Runnable(){public void run(){refreshStatus();handler.postDelayed(this,1500);}};
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        ScrollView scroll=new ScrollView(this);
        LinearLayout layout=new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL); layout.setPadding(32,64,32,32); layout.setBackgroundColor(Color.rgb(246,249,241));scroll.addView(layout);setContentView(scroll);
        TextView title=new TextView(this);title.setText("CourseInbox\n手机通知伴侣");title.setTextSize(27);title.setTextColor(Color.rgb(42,83,51));layout.addView(title);
        text(layout,"只接收白名单应用的系统通知。任务需在电脑收件箱核对；不会读取应用内历史或代交作业。");
        SharedPreferences prefs=NotificationQueue.preferences(this);
        server=field(layout,"电脑服务地址",prefs.getString("server","http://192.168.1.100:8765"),false);
        token=field(layout,"访问令牌",prefs.getString("token",""),true);
        scope=field(layout,"班级 / 分组",prefs.getString("scope",""),false);
        packages=field(layout,"应用白名单（包名，每行一个）",prefs.getString("packages","com.chaoxing.mobile"),false);packages.setSingleLine(false);packages.setMinLines(2);
        button(layout,"保存配置",()->{
            try {
                if (!NotificationQueue.allowedEndpoint(new URI(server.getText().toString().trim()))) throw new IllegalArgumentException();
                if(token.getText().toString().trim().length()<24)throw new IllegalArgumentException();
                prefs.edit().putString("server",server.getText().toString().trim()).putString("token",token.getText().toString().trim()).putString("scope",scope.getText().toString().trim()).putString("packages",packages.getText().toString().trim()).commit();
                Toast.makeText(this,"配置已保存",Toast.LENGTH_SHORT).show(); NotificationQueue.flush(this);
            } catch(Exception error) { Toast.makeText(this,"请检查服务地址及至少24字符的令牌",Toast.LENGTH_LONG).show(); }
        });
        button(layout,"授权通知访问",()->startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        button(layout,"立即重试补传",()->{NotificationQueue.flush(this);refreshStatus();});
        button(layout,"发送示例通知事件",()->{
            try {
                JSONObject event=new JSONObject();event.put("package_name","com.chaoxing.mobile");event.put("notification_key","demo:"+System.currentTimeMillis());event.put("title","《手机联调示例》 第一次作业");event.put("text","示例数据：请明天18:00前提交实验报告。");event.put("captured_at",CourseNotificationService.timestamp(System.currentTimeMillis()));event.put("scope",prefs.getString("scope",""));
                NotificationQueue.enqueue(this,event);NotificationQueue.flush(this);refreshStatus();
            }catch(Exception error){Toast.makeText(this,"示例事件构造失败",Toast.LENGTH_SHORT).show();}
        });
        status=new TextView(this);status.setPadding(0,24,0,16);status.setTextSize(14);layout.addView(status);
        button(layout,"清空待传队列",()->new AlertDialog.Builder(this).setTitle("清空未发送事件？").setMessage("这会删除手机上的未发送通知。电脑已收到的消息不受影响。").setNegativeButton("取消",null).setPositiveButton("清空",(dialog,which)->{NotificationQueue.clear(this);refreshStatus();}).show());
        text(layout,"电脑默认仅本机访问。局域网配对前运行 start-lan.cmd。HTTP 仅用于可信局域网，远程服务请使用 HTTPS。\n\n电脑不在线时保存最多200条事件。客户端打开、监听连接或新通知到来时尝试上传；不保证系统休眠时定时重试。");
    }
    private void text(LinearLayout layout,String text){TextView label=new TextView(this);label.setText(text);label.setTextSize(13);label.setTextColor(Color.rgb(111,135,96));label.setPadding(0,18,0,14);layout.addView(label);}
    private EditText field(LinearLayout layout,String name,String value,boolean password){text(layout,name);EditText edit=new EditText(this);edit.setText(value);edit.setTextSize(14);edit.setSingleLine(true);if(password)edit.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);layout.addView(edit);return edit;}
    private void button(LinearLayout layout,String name,Runnable action){Button button=new Button(this);button.setText(name);button.setAllCaps(false);button.setOnClickListener(v->action.run());layout.addView(button);}
    private void refreshStatus(){if(status==null)return;SharedPreferences prefs=NotificationQueue.preferences(this);status.setText("待传事件："+NotificationQueue.count(this)+"\n"+prefs.getString("listener_status","尚未连接通知监听，请授权")+"\n"+prefs.getString("last_status","等待一条新通知")+"\n队列满时未保存："+prefs.getInt("dropped",0)+" 条");}
    @Override protected void onResume(){super.onResume();handler.post(update);NotificationQueue.flush(this);}
    @Override protected void onPause(){super.onPause();handler.removeCallbacks(update);}
}
