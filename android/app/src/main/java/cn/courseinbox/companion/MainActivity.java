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
    private EditText server,token,scope,packages,computerName;
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
        computerName=field(layout,"电脑配对名称（电脑页面复制；可留空）",prefs.getString("target_name",""),false);
        server=field(layout,"当前电脑地址（自动寻找成功后更新；也可手动填写）",prefs.getString("server","http://192.168.1.100:8765"),false);
        token=field(layout,"访问令牌",prefs.getString("token",""),true);
        scope=field(layout,"班级 / 分组",prefs.getString("scope",""),false);
        packages=field(layout,"应用白名单（包名，每行一个）",prefs.getString("packages","com.chaoxing.mobile"),false);packages.setSingleLine(false);packages.setMinLines(2);
        button(layout,"保存配置",()->{if(saveConfiguration())NotificationQueue.flush(this);});
        button(layout,"自动寻找并配对电脑",()->{if(saveConfiguration()){NotificationQueue.pair(this);refreshStatus();}});
        button(layout,"重新配对另一台电脑",()->new AlertDialog.Builder(this).setTitle("更换已配对电脑？")
            .setMessage("将解除原电脑身份，保留待传消息。请填写新电脑名称和令牌，再点击自动寻找并配对。")
            .setNegativeButton("取消",null).setPositiveButton("解除配对",(dialog,which)->{
                synchronized(ComputerDiscovery.CONFIG_LOCK){prefs.edit().remove("paired_device_id").remove("paired_name").putBoolean("pairing_required",true)
                    .putInt("config_generation",prefs.getInt("config_generation",0)+1).putString("last_status","已解除原电脑配对，消息保留；请重新配对。").commit();}
                computerName.setText("");refreshStatus();
            }).show());
        button(layout,"授权通知访问",()->startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        button(layout,"立即重试补传",()->{NotificationQueue.flush(this);refreshStatus();});
        button(layout,"发送示例通知事件",()->{
            try {
                JSONObject event=new JSONObject();event.put("package_name","com.chaoxing.mobile");event.put("notification_key","demo:"+System.currentTimeMillis());event.put("title","【手机伴侣示例】 第一次作业");event.put("text","示例内容：请明天18:00前提交实验报告。");event.put("captured_at",CourseNotificationService.timestamp(System.currentTimeMillis()));event.put("scope",prefs.getString("scope",""));
                NotificationQueue.enqueue(this,event);NotificationQueue.flush(this);refreshStatus();
            }catch(Exception error){Toast.makeText(this,"示例事件创建失败",Toast.LENGTH_SHORT).show();}
        });
        status=new TextView(this);status.setPadding(0,24,0,16);status.setTextSize(14);layout.addView(status);
        button(layout,"清空待传队列",()->new AlertDialog.Builder(this).setTitle("清空未发送事件？").setMessage("将删除手机上的未发送通知；电脑已收到的消息不受影响。")
            .setNegativeButton("取消",null).setPositiveButton("清空",(dialog,which)->{NotificationQueue.clear(this);refreshStatus();}).show());
        text(layout,"电脑运行 start-lan.cmd，并保持启动窗口打开。首次安装自动发现组件见电脑页面。配对后地址变化时会寻找同一台电脑；校园网屏蔽发现时需手动更新当前地址。HTTP 仅用于可信局域网。\n\n电脑不在线时保存最多200条事件。客户端打开、监听连接或新通知到来时尝试补传；不保证系统休眠时定时重试。0.2.0");
    }
    private boolean saveConfiguration() {
        SharedPreferences prefs=NotificationQueue.preferences(this);
        try {
            String endpoint=server.getText().toString().trim(),secret=token.getText().toString().trim(),name=computerName.getText().toString().trim();
            if((!endpoint.isEmpty()&&!NotificationQueue.allowedEndpoint(new URI(endpoint)))||secret.length()<24||(!name.isEmpty()&&!name.matches("CourseInbox-[0-9a-f]{8}")))throw new IllegalArgumentException();
            synchronized(ComputerDiscovery.CONFIG_LOCK) {
                boolean changed=!endpoint.equals(prefs.getString("server",""))||!secret.equals(prefs.getString("token",""))||!name.equals(prefs.getString("target_name",""));
                boolean changedToken=!secret.equals(prefs.getString("token",""))&&!prefs.getString("paired_device_id","").isEmpty();
                SharedPreferences.Editor editor=prefs.edit().putString("server",endpoint).putString("token",secret).putString("target_name",name)
                    .putString("scope",scope.getText().toString().trim()).putString("packages",packages.getText().toString().trim());
                if(changed)editor.putInt("config_generation",prefs.getInt("config_generation",0)+1);
                if(changedToken)editor.putBoolean("pairing_required",true);
                if(!editor.commit())throw new IllegalStateException();
            }
            Toast.makeText(this,"配置已保存",Toast.LENGTH_SHORT).show();return true;
        } catch(Exception error){Toast.makeText(this,"请检查地址、至少24字符的令牌和电脑配对名称",Toast.LENGTH_LONG).show();return false;}
    }
    private void text(LinearLayout layout,String text){TextView label=new TextView(this);label.setText(text);label.setTextSize(13);label.setTextColor(Color.rgb(111,135,96));label.setPadding(0,18,0,14);layout.addView(label);}
    private EditText field(LinearLayout layout,String name,String value,boolean password){text(layout,name);EditText edit=new EditText(this);edit.setText(value);edit.setTextSize(14);edit.setSingleLine(true);if(password)edit.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);layout.addView(edit);return edit;}
    private void button(LinearLayout layout,String name,Runnable action){Button button=new Button(this);button.setText(name);button.setAllCaps(false);button.setOnClickListener(v->action.run());layout.addView(button);}
    private void refreshStatus(){
        if(status==null)return;SharedPreferences prefs=NotificationQueue.preferences(this);
        String paired=prefs.getString("paired_name","");
        status.setText("配对电脑："+(paired.isEmpty()?"尚未配对":paired)+(prefs.getBoolean("pairing_required",false)?"（需重新配对）":"")+"\n待传事件："+NotificationQueue.count(this)+"\n"+prefs.getString("listener_status","尚未连接通知监听，请授权")+"\n"+prefs.getString("last_status","等待一条新通知")+"\n队列满时未保存："+prefs.getInt("dropped",0)+" 条");
        if(!server.hasFocus()&&!paired.isEmpty()&&!prefs.getBoolean("pairing_required",false)) {
            String endpoint=prefs.getString("server","");if(!endpoint.contentEquals(server.getText()))server.setText(endpoint);
        }
    }
    @Override protected void onResume(){super.onResume();handler.post(update);NotificationQueue.flush(this);}
    @Override protected void onPause(){super.onPause();handler.removeCallbacks(update);}
}
